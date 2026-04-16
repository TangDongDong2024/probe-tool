# -*- coding: utf-8 -*-
"""
HTTP下载探测模块 (probe_httpdown_fast.py)
=====================================

功能描述:
    本模块提供HTTP/HTTPS下载探测功能，用于检测目标URL的可达性、
    响应速度、下载状态等关键指标。

主要功能:
    1. HTTP/HTTPS请求探测
    2. DNS封堵检测
    3. 访问跳转检测
    4. 响应时间统计
    5. IP归属地查询

性能优化:
    - HTTP请求与DNS检查并行执行
    - DNS查询采用asyncio.gather并行查询本地DNS和公共DNS
    - curl命令参数优化（去除冗余输出参数）

错误码定义:
    - 0: 访问成功
    - 1001: DNS解析失败
    - 1002: TCP连接失败
    - 1003: SSL协商失败
    - 1004: 连接被重置
    - 1005: 服务端传输超时
    - 1006: 访问超时（7秒）
    - 1007: 重定向次数过多
    - 1008: URL格式错误
    - 1009: 跳转到反诈网站
    - 1010: 重定向至异常IP
    - 1011: DNS封堵
    - 1012: 测试总超时（13秒）
    - 1099: 未知失败

使用示例:
    ```python
    python probe_httpdown_fast.py result.json 4 https://example.com/
    ```

参数说明:
    sys.argv[1]: 输出文件路径
    sys.argv[2]: IP协议类型 (4=IPv4, 6=IPv6)
    sys.argv[3]: 目标URL
    sys.argv[4]: DNS服务器（可选）
"""

import asyncio
import json
import subprocess
import sys
import os
import re
import time
import gzip
import concurrent.futures
import ip_utils
from probe_dns_block import DomainBlockChecker


class Probe_HttpDown(object):
    """
    HTTP下载探测器类

    功能说明:
        封装HTTP探测全流程，包括DNS检查、HTTP请求、结果解析和写入。
        支持IPv4/IPv6，自动检测DNS封堵和访问跳转。

    性能特性:
        - DNS检查与HTTP请求并行执行
        - DNS查询本地DNS和公共DNS并行
        - 超时控制完善
    """

    def __init__(self,test_url,out_file,ip_type,dnsserver:str=""):
        self.test_url=test_url
        self.timeout=8
        self.dnsserver=dnsserver
        self.out_file=out_file
        self.ip_type=ip_type
        self.result_dict={"time_namelookup":-1,"time_connect":-1,"time_appconnect":-1,"time_redirect":-1,"time_pretransfer":-1,"time_starttransfer":-1,"time_total":-1,"remote_ip":"","response_code":0,"size_download":-1,"speed_download":-1,"ip_info":{},"urle_host":"","dns_block":-1,"code":-1,"is_success":0,"num_redirects":0}
        # 初始化result_code，避免后续使用时未定义
        self.result_code = -1
        if self.ip_type==6:
            self.result_dict["remote_ip"]="::"
        elif self.ip_type==4:
            self.result_dict["remote_ip"]="0.0.0.0"

    # 封堵IP黑名单（与probe_dns_block.py保持一致）
    BLOCKED_IPS_v4 = ['0.0.0.0', '127.0.0.1', '183.252.183.9', '183.252.183.98', '182.43.124.6']
    BLOCKED_IPS_v6 = ['::1', '::', '::0', 'FE80::1', '2409:8034:3830:42::4']

    def _is_blocked_ip(self, ip: str, ip_type: int) -> bool:
        """
        判断IP是否为封堵IP

        参数说明:
            ip (str): 待检测的IP地址
            ip_type (int): IP协议类型 - 4:IPv4, 6:IPv6

        返回值:
            bool: True表示是封堵IP，False表示正常IP
        """
        if ip_type == 4:
            return ip in self.BLOCKED_IPS_v4
        elif ip_type == 6:
            return ip in self.BLOCKED_IPS_v6
        else:
            # 双栈模式：IPv4和IPv6封堵IP都算
            return ip in self.BLOCKED_IPS_v4 or ip in self.BLOCKED_IPS_v6

    async def check_dns_block(self, domain):
        """
        DNS封堵检测

        功能说明:
            调用DomainBlockChecker检测域名是否被DNS封堵
        """
        checker = DomainBlockChecker(self.dnsserver)
        ret, localresult = await checker.check_dns_blocking(domain, self.ip_type)

        if ret:
            # DNS封堵
            self.result_dict["dns_block"] = 1
            self.result_dict["is_success"] = 0
            self.result_dict["response_code"] = 1011
        else:
            self.result_dict["dns_block"] = 0

        # 查找有效的非封堵IP作为remote_ip
        # 只有当remote_ip为空或已被设置为封堵IP时才更新
        if self.result_dict["remote_ip"] == "" or self._is_blocked_ip(self.result_dict["remote_ip"], self.ip_type):
            valid_ip_found = False
            for dns_result in localresult:
                # 跳过封堵IP
                if self._is_blocked_ip(dns_result, self.ip_type):
                    continue

                # 检查IP类型是否匹配
                if self.ip_type == 6 and ":" in dns_result:
                    self.result_dict["remote_ip"] = dns_result
                    valid_ip_found = True
                    break
                elif self.ip_type == 4 and "." in dns_result:
                    self.result_dict["remote_ip"] = dns_result
                    valid_ip_found = True
                    break

            # 如果没有找到有效IP，设置默认值
            if not valid_ip_found:
                if self.ip_type == 6:
                    self.result_dict["remote_ip"] = "::"
                elif self.ip_type == 4:
                    self.result_dict["remote_ip"] = "0.0.0.0"

    def check_jump_block(self):
        if self.result_dict["num_redirects"]>0:

            # 最终目标是封堵网站
            if  self.result_dict["urle_host"] in ["0.0.0.0", "127.0.0.1", '::1', '::', '::0', 'FE80::1']:
                self.result_dict["is_success"] = 0
                self.result_dict["dns_block"] = 1
                self.result_dict["code"] = 1010
                self.result_dict["response_code"] = 1010
            else:
                if self.result_dict["code"]>0:
                    if self.result_dict["response_code"] != 200:
                        self.result_dict["is_success"] = 0
                    if self.result_dict["code"]==1001:
                        if self.ip_type == 4:
                            self.result_dict["remote_ip"]="0.0.0.0"
                        elif self.ip_type == 6:
                            self.result_dict["remote_ip"]="::"
                else:
                    if self.result_dict["response_code"]!=200:
                        self.result_dict["response_code"] = 301
        # # 最终目标是封堵网站
        # if self.result_dict["response_code"]==301 and self.result_dict["urle_host"] in ["0.0.0.0", "127.0.0.1", '::1', '::', '::0', 'FE80::1']:
        #     self.result_dict["dns_block"] = 1
        #     self.result_dict["code"] = 1010
        #     self.result_dict["response_code"] = 1010
        # 最终目标是反诈网站
        if self.result_dict["remote_ip"] in ["183.252.183.98","183.252.183.9","182.43.124.6","2409:8034:3830:42::4"]:
            self.result_dict["is_success"] = 0
            self.result_dict["dns_block"] = 1
            self.result_dict["code"] = 1009
            self.result_dict["response_code"]=1009


    def write_result_file(self):
        strjson=json.dumps(self.result_dict,ensure_ascii=False)
        with open (self.out_file, mode='w', encoding='utf-8') as f:
            f.write (strjson)

    def parse_probe_stderr(self,raw_out):
        # print ("probe_result_stderr:{}", raw_out)
        try:
            lines_out = raw_out.split ("\n")
            host_ip=""
            for line in lines_out:
                if " *   Trying " in line:
                    print("found Trying",line)
                    if "[" in line and "]" in line:
                        match_ips = re.findall (r'Trying \[(.*?)\]:(.*)...', line)
                        if len (match_ips) > 0:
                            print (match_ips)
                            host_ip = match_ips[0][0]
                            print ("Trying host ip:", host_ip)
                        else:
                            print ("no match Trying")
                    else:
                        match_ips = re.findall (r'Trying (.*?):(.*)...', line)
                        if len (match_ips) > 0:
                            print(match_ips)
                            host_ip=match_ips[0][0]
                            print ("Trying host ip:", host_ip)
                        else:
                            print("no match Trying")

            if len (host_ip) > 0:
                self.result_dict["remote_ip"] = host_ip.upper ()
        except Exception as e:
            print("parse_probe_stderr error:",e)

    def check_success(self,parsed_dict):
        """
        根据curl返回码判断访问是否成功

        错误码映射:
            curl返回码 -> 内部错误码
            0 -> 0 (成功)
            3 -> 1008 (URL格式错误)
            6 -> 1001 (DNS解析失败)
            7 -> 1002 (TCP连接失败)
            28 -> 1005/1006 (超时)
            35 -> 1003 (SSL失败)
            47 -> 1007 (重定向过多)
            52 -> 1005 (服务器无响应)
            56 -> 1004 (连接被重置)
        """
        # 1001:DNS解析失败
        # 1002:TCP连接失败
        # 1003: SSL协商失败
        # 1004: 连接被重置
        # 1005: 服务端传输5秒超时
        # 1006：访问时间7秒超时
        # 1007：重定向次数过多
        # 1008：URL格式错误
        # 1009：跳转到反诈网站（183.252.183.98、183.252.183.9、182.43.124.6（电信反诈）、2409:8034:3830:42::4）以及识别响应报文含有“警方提示疑似诈骗”的报文特征。
        # 1010：跳转后重定向至0.0.0.0、127.0.0.1这类异常IP。
        # 1011：运营商DNS解析域名为封堵IP，公共DNS解析含正常IP。
        # 1012：测试总时间13秒超时
        # 1099：未知失败原因
        if self.result_code == 0:
            if self.result_dict["response_code"] > 199 and self.result_dict["response_code"] < 400:
                self.result_dict["is_success"] = 1
            else:
                self.result_dict["is_success"] = 0
            self.result_dict["code"] = 0
        else:
            if self.result_code == 3:
                self.result_dict["code"] = 1008
                print("URL格式错误")
            elif self.result_code == 6:
                self.result_dict["code"] = 1001
                print("DNS解析失败")
            elif self.result_code == 7:
                # -9002	TCP连接失败
                self.result_dict["code"] = 1002
                print("TCP连接失败")
            elif self.result_code == 28:
                if parsed_dict["time_total"]>=7000:
                    self.result_dict["code"] = 1006
                    print("操作7秒超时")
                else:
                    if parsed_dict["errormsg"].startswith("Connection timed out"):
                        self.result_dict["code"] = 1002
                    elif parsed_dict["errormsg"].startswith("Operation too slow"):
                        self.result_dict["code"] = 1005
                    elif parsed_dict["errormsg"].startswith("Resolving timed out"):
                        self.result_dict["code"] = 1001
                    else:
                        self.result_dict["code"] = 1099
                errmsg = parsed_dict["errormsg"]
                print(f"操作超时{errmsg}")
            elif self.result_code == 35:
                # -9005	SSL连接失败
                self.result_dict["code"] = 1003
            elif self.result_code == 47:
                # -9009   重定向后请求失败
                self.result_dict["code"] = 1007
            elif self.result_code == 52:
                # -9003	GET请求响应超时
                self.result_dict["code"] = 1005
                print("服务器无响应")
            elif self.result_code == 56:
                self.result_dict["code"] = 1004
                print("接收失败: 连接被重置")
            else:
                print("未知失败原因")
                self.result_dict["code"] = 1099
            http_code=parsed_dict["response_code"]
            print(f"程序执行返回码:{self.result_code},HTTP状态码：{http_code}")
            self.result_dict["is_success"] = 0
            if http_code == 0:
                self.result_dict["response_code"] = self.result_dict["code"]

            if self.result_dict["response_code"] > 199 and self.result_dict["response_code"] < 400:
                self.result_dict["is_success"] = 1
            print("check_success over. probe_result :{}".format(self.result_dict))
    def check_outfile(self, outfile):
        """
        检查下载的响应文件内容

        功能说明:
            1. 检查文件大小（小于512字节可能是错误页面）
            2. 尝试解压gzip压缩内容
            3. 检测"警方提示疑似诈骗"特征
            4. 检测完成后删除临时文件

        参数说明:
            outfile (str): curl下载的临时文件路径
        """
        # 检查文件是否存在
        if not os.path.exists(outfile):
            print(f"文件 {outfile} 不存在，跳过检查")
            return
        
        try:
            # 检查文件大小是否小于0.5KB
            if os.path.getsize(outfile) < 512:
                with open(outfile,mode='rb') as f:  # 修改为二进制模式
                    raw_bytes = f.read()
                    raw_out=""
                    try: # 尝试解压gzip数据
                        decompressed_bytes = gzip.decompress(raw_bytes)
                        raw_out = decompressed_bytes.decode('utf-8', errors='ignore')
                    except Exception as e: # 解压失败则直接解码原始字节
                        raw_out = raw_bytes.decode('utf-8', errors='ignore')
                    print(f"raw_out:{raw_out}")
                    if "警方提示疑似诈骗" in raw_out:
                        print("警方提示疑似诈骗")
                        self.result_dict["is_success"] = 0
                        self.result_dict["code"] = 1009
                        self.result_dict["response_code"] = 1009
            # 只在文件存在时才尝试删除
            try:
                os.remove(outfile)
                print(f"临时文件已删除: {outfile}")
            except Exception as e:
                print(f"删除临时文件失败: {e}")
        except Exception as e:
            print(f"检查输出文件时出错: {e}")

    def parse_probe_result(self,raw_out):
        try:
            print("probe_result_stdout:{}",raw_out)
            lines_out = raw_out.split ("\n")
            host_ip = ""
            res_dict={}
            secondkeys=["time_queue","time_namelookup","time_connect","time_appconnect","time_redirect","time_pretransfer","time_starttransfer","time_total"]
            floatkeys=["speed_download"]
            intkeys=["size_download","num_connects","num_redirects","exitcode","response_code"]
            for line in lines_out:
                if "[" in line and "]" in line:
                    print("line:",line.strip())
                    keyvalues=line.split(":",1)
                    # print(keyvalues)
                    # match_ips = re.findall (r'(.*?)\]', keyvalues[1])
                    match_ips = re.findall (r'\[(.*?)\]',keyvalues[1] )
                    if len(match_ips)>0:
                        value=match_ips[0]
                        key=keyvalues[0].strip ()
                        if key=="remote_ip":
                            res_dict[key] = value
                            host_ip=value
                        elif key=="errormsg":
                            res_dict[key] = value
                        elif key=="urle_host":
                            res_dict[key] = value
                        elif key in secondkeys:
                            res_dict[key] =int(1000*float(value))
                        elif key in floatkeys:
                            res_dict[key] =  float (value)
                        elif key in intkeys:
                            res_dict[key] = int (value)
                    else:
                        print("no found")
                else:
                    pass
            print("res_dict:%s" % (res_dict))
            print("host_ip:{}",self.result_dict["remote_ip"])

            # 使用.get()方法安全访问字典键，避免KeyError
            if "time_connect" in res_dict and res_dict.get("time_connect", 0) > 0:
                self.result_dict["time_connect"] = (res_dict.get("time_connect", 0) - res_dict.get("time_namelookup", 0))
            else:
                self.result_dict["time_connect"]=0
            
            if res_dict.get("time_namelookup", 0) > res_dict.get("time_queue", 0):
                self.result_dict["time_namelookup"] = res_dict.get("time_namelookup", 0) - res_dict.get("time_queue", 0)
            else:
                self.result_dict["time_namelookup"] = 0
            
            if res_dict.get("time_appconnect", 0) > 0:
                if res_dict.get("time_appconnect", 0) > res_dict.get("time_connect", 0):
                    self.result_dict["time_appconnect"] = res_dict.get("time_appconnect", 0) - res_dict.get("time_connect", 0)
                else:
                    self.result_dict["time_appconnect"] = res_dict.get("time_appconnect", 0)
            else:
                self.result_dict["time_appconnect"] =0

            if res_dict.get("size_download", 0) < 0:
                res_dict["size_download"] = 0
            if res_dict.get("speed_download", 0) < 0:
                res_dict["speed_download"] = 0
            self.result_dict["time_redirect"] = res_dict.get("time_redirect", 0)
            self.result_dict["time_pretransfer"] = res_dict.get("time_pretransfer", 0)
            self.result_dict["time_starttransfer"] = res_dict.get("time_starttransfer", 0)
            self.result_dict["time_total"] = res_dict.get("time_total", 0)
            self.result_dict["response_code"] = res_dict.get("response_code", 0)
            self.result_dict["size_download"] = res_dict.get("size_download", 0)
            self.result_dict["speed_download"] = res_dict.get("speed_download", 0) / 1024
            self.result_dict["urle_host"] = res_dict.get("urle_host", "")
            
            if "response_code" in res_dict and res_dict.get("response_code", 0) > 0:
                self.result_dict["response_code"] = res_dict["response_code"]
            if "num_redirects" in res_dict and res_dict.get("num_redirects", 0) > 0:
                self.result_dict["num_redirects"] = res_dict["num_redirects"]
            
            if len (self.result_dict["remote_ip"]) > 0:
                ip_finder_obj = ip_utils.ip_finder ("nettest_ipaddress.db", "respone_relation.txt")
                self.result_dict["ip_info"] = ip_finder_obj.find_main_ip (self.result_dict["remote_ip"])
            self.check_success(res_dict)
        except Exception as e:
            print("parse_result_error:%s" % (e))






# 失败码	-9001	DNS解析失败
# -9002	TCP连接失败
# -9003	GET请求响应超时
# -9004	GET请求返回非200OK
# -9005	SSL连接失败
# -9009   重定向后请求失败
# -1	    访问成功    	DNS响应超时时间：2.5秒
# TCP连接超时时间：10秒
# GET响应超时时间：10秒
# 2XX 3XX也是成功。重定向20次算失败记为-9009。


    async def start_probe(self):
        """
        启动HTTP探测（主流程）

        功能说明:
            1. 构建curl命令
            2. 并行执行HTTP请求和DNS检查
            3. 解析curl输出
            4. 检查跳转和封堵
            5. 写入结果文件

        性能优化:
            - HTTP请求在ThreadPoolExecutor中执行
            - DNS检查异步执行
            - 两者并行执行，减少总耗时
        """
        formatstr='''
          num_connects:  [%{num_connects}] 
         num_redirects:  [%{num_redirects}] 
            time_queue:  [%{time_queue}]    
       time_namelookup:  [%{time_namelookup}]
          time_connect:  [%{time_connect}]
       time_appconnect:  [%{time_appconnect}]
         time_redirect:  [%{time_redirect}]
      time_pretransfer:  [%{time_pretransfer}]
    time_starttransfer:  [%{time_starttransfer}]
            time_total:  [%{time_total}]
         response_code:  [%{response_code}]
             remote_ip:  [%{remote_ip}]
         size_download:  [%{size_download}]
        speed_download:  [%{speed_download}]
              errormsg:  [%{errormsg}]
              exitcode:  [%{exitcode}]
             urle_host:  [%{urle.host}]
'''

        # 创建 fastgettmp 目录（如果目录不存在）
        output_dir = os.path.join(os.getcwd(), "fastgettmp")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 使用时间戳生成唯一的文件名
        timestamp = int(time.time())
        output_file = os.path.join(output_dir, f"output_{timestamp}.txt")

        # 获取当前工作目录
        current_dir = os.getcwd()
        curl_path = os.path.join(current_dir, "curl2.exe")

        # 使用拼接后的curl路径
        cmd = [
            curl_path, "-X", "GET", "-L", "-m", "7", "--trace-time",
            "--max-redirs", "20", "--connect-timeout", "3", "--speed-limit", "1",
            "--speed-time", "5", "-k", "-o", output_file, "-w", formatstr,
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "-H", "Accept-Language: zh-CN,zh;q=0.9",
            "-H", "Accept-Encoding: gzip, deflate, br",
            self.test_url
        ]

        if self.ip_type == 4:
            cmd.insert(3, "-4")
        elif self.ip_type == 6:
            cmd.insert(3, "-6")
        if  self.dnsserver is not None and self.dnsserver != "":
            cmd.insert(1, "--dns-servers")
            cmd.insert(2, self.dnsserver)
        print(cmd)
        
        # ========== 并行化优化 ==========
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        http_future = None
        dns_future = None
        execution_error = None

        try:
            # 并行执行：HTTP请求 和 DNS检查
            http_future = loop.run_in_executor(executor, self.run_curl_request, cmd, output_file)
            # DNS检查协程需要包装为任务
            dns_future = asyncio.create_task(self.check_dns_block(self.test_url))

            # 等待两个任务完成
            done, pending = await asyncio.wait(
                [http_future, dns_future],
                timeout=5.0,
                return_when=asyncio.ALL_COMPLETED
            )
            
            # 检查执行结果
            for task in done:
                try:
                    task.result()
                except Exception as e:
                    execution_error = e
                    print(f"并行任务执行出错: {e}")
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
                
        except Exception as e:
            print(f"并行执行出错: {e}")
            execution_error = e
        finally:
            # 等待任务真正完成后关闭线程池
            executor.shutdown(wait=True)
        
        # 异常情况下标记结果
        if execution_error is not None:
            self.result_dict["code"] = 1099
            self.result_dict["is_success"] = 0
        
        self.check_jump_block()
        self.check_outfile(output_file)
        print("probe_result formated:{}".format(self.result_dict))
        self.write_result_file()
    
    def run_curl_request(self, cmd, output_file):
        """
        执行curl请求（同步方法，在线程池中运行）

        参数说明:
            cmd (list): curl命令参数列表
            output_file (str): 下载输出文件路径

        返回值:
            bool: 是否超时
        """
        start_time = time.time()
        cmd_run_timeout = False
        completed_process = None
        try:
            completed_process = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8')
        except subprocess.TimeoutExpired:
            cmd_run_timeout = True
            print("cmd run timeout")

        if completed_process is not None:
            self.result_code = completed_process.returncode
            stdout = completed_process.stdout
            stderr = completed_process.stderr
        else:
            self.result_code = -1
            stdout = ""
            stderr = ""
        
        over_time = (time.time())
        if self.result_code >= 0:
            print("run time:{}", over_time - start_time)
            print("returncode:", self.result_code)

            raw_out = stdout
            err_out = stderr
            self.parse_probe_stderr(err_out)
            self.parse_probe_result(raw_out)
        
        if cmd_run_timeout:
            self.result_dict["response_code"] = 1012
        
        return cmd_run_timeout











if __name__ == '__main__':
    app_start_time = time.time ()
    this = os.path.abspath (os.path.dirname (__file__))
    module = os.path.split (this)[0]
    print ('sys.path.append("%s")' % module)
    sys.path.append (module)
    for i, val in enumerate (sys.path):
        print ("[%s] %s" % (i + 1, val))

    print ('参数个数为:', len (sys.argv), '个参数。')
    print ('参数列表:', str (sys.argv))
    print ('脚本名:', str (sys.argv[0]))

    print ('__file__:', __file__)
    print ('sys.executable:', sys.executable)
    print ('sys.argv[0]:', sys.argv[0])
    print ('os.getcwd():', os.getcwd ())
    print ('sys.frozen:', getattr (sys, 'frozen', False))
    print ('sys._MEIPASS:', getattr (sys, '_MEIPASS', None))

    # 安全检查参数个数
    if len(sys.argv) < 4:
        print("错误: 参数不足！用法: probe_httpdown_fast.exe <输出文件> <IP类型> <URL> [DNS服务器]")
        print("  示例: probe_httpdown_fast.exe result.json 4 https://zxgk.court.gov.cn/")
        sys.exit(1)
    
    testurl= sys.argv[3] if len(sys.argv) > 3 else ""
    ip_type=int(sys.argv[2]) if len(sys.argv) > 2 else 4
    outfile=sys.argv[1]
    dnsserver=""
    if len(sys.argv) >= 5:
        dnsserver = sys.argv[4]
    elif len(sys.argv) == 4:
        dnsserver = ""
    if DomainBlockChecker.is_valid_ip_address(testurl) and ':' in testurl:
        testurl=f"[{testurl}]"
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    probe_obj = Probe_HttpDown (testurl, outfile,ip_type,dnsserver)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(probe_obj.start_probe())
        loop.close()
    except KeyboardInterrupt:
        print("User interrupted.")
    # asyncio.run(probe_obj.start_probe())
    app_end_time = time.time ()
    cost_time = app_end_time - app_start_time
    print("Application run time: %.2f seconds" % (cost_time))
