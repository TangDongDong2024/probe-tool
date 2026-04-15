import ipaddress
import sys
import os
import time
import json
import ip_utils
import statistics  # 添加statistics库用于计算平均值和标准差
import asyncio
import socket
from probe_dns_block import DNSServer
class Probe_Tcping(object):
    def __init__(self, host, out_file, tcping_port, ip_type, dnserver:str="",request_count=10, timeout_per_request=1, total_timeout=60):
        self.host=host
        self.out_file = out_file
        self.tcping_port = tcping_port
        self.result_code = -1
        self.ip_type = ip_type
        self.local_dns_server = dnserver
        self.request_count = request_count  # 添加请求次数参数
        self.timeout_per_request = timeout_per_request  # 添加每次响应超时时间参数
        self.total_timeout = total_timeout  # 添加总测试超时时间参数
        self.result_dict = {
            "code": -1,
            "host_ip": "0.0.0.0",
            "ip_info": {"ip_operator": "", "ip_province": "", "ip_city": ""},
            "tcping_port": tcping_port,
            "tcping_detail": "",
            "min_latency": 0.0,
            "max_latency": 0.0,
            "avg_latency": 0.0,
            "packet_loss_rate": 100.0,
            "jitter": 0.0,
            "request_count": self.request_count,  # 添加请求次数字段
            "success_count": 0  # 添加成功响应次数字段
        }
        if self.ip_type==6:
            self.result_dict["host_ip"] = "::"
        self.latencies = []  # 添加latency列表用于存储每次请求的延迟
        self.write_result_file()

    def write_result_file(self):
        strjson = json.dumps(self.result_dict, ensure_ascii=False)
        with open(self.out_file, mode='w', encoding='utf-8') as f:
            f.write(strjson)

    def is_valid_ip_address(self,address):
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False
    async def get_destip(self):
        start_time = time.time()
        try:
            if self.is_valid_ip_address(self.host):
                self.host = self.host
            else:
                localdnsservers=[]
                if len(self.local_dns_server)>0:
                    localdnsservers.append(self.local_dns_server)
                dns_queryer = DNSServer(0.5, localdnsservers)
                time_dns_query = time.time()
                local_results = await dns_queryer.query(localdnsservers, self.host, self.ip_type)  # 使用await等待协程完成
                if local_results and len(local_results)>0:
                    self.host = local_results[0]
                else:
                    self.result_dict["code"] = -2
        except asyncio.TimeoutError:
            print("Total timeout exceeded")
            self.result_dict["code"] = -3  # 添加超时错误码
        over_time = time.time()
        print("run time:{}", over_time - start_time)
    async def run_tcping(self):
        start_time = time.time()
        try:
            # 修改解析主机名的方式以支持IPv6
            # self.host = socket.getaddrinfo(host, None, family=socket.AF_INET6 if self.ip_type == 6 else socket.AF_INET)[0][-1][0]
            await self.get_destip()
            await asyncio.gather(*(self.ping_host() for _ in range(self.request_count)))
        except socket.gaierror as e:
            print(f"Error resolving host: {e}")

            self.host = "0.0.0.0"  # 如果解析失败，保留原始host
            if ip_type==6:
                self.host = "::"
            self.result_dict["code"] = -2
        over_time = time.time()
        print("run time:{}", over_time - start_time)
        print("latencies collected:", self.latencies)  # 添加日志以确保latencies被正确收集
        self.result_code = 0 if any(self.latencies) else -1  # 修改判断条件，确保只要有非零时延就认为成功
        print("returncode:", self.result_code)
        print("latencies:", self.latencies)
        self.result_dict["success_count"] = len([latency for latency in self.latencies if latency > 0])  # 计算成功响应次数
        self.parse_tcping(self.latencies)
        self.write_result_file()

    async def ping_host(self):
        try:
            start = time.time()
            # 指定地址族以支持IPv6
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.tcping_port, family=socket.AF_INET6 if self.ip_type == 6 else socket.AF_INET), timeout=self.timeout_per_request)

            writer.close()
            await writer.wait_closed()
            end = time.time()
            latency = (end - start) * 1000  # 计算延迟并转换为毫秒
            latency = round(latency, 2)  # 格式化延迟为小数点后两位
            self.latencies.append(latency)
            print(f"Latency collected: {latency} ms")  # 添加日志以确保每次请求的结果都被正确收集
        except Exception as e:
            print(f"Error during ping: {e}")
            latency = 0.0  # 确保latency被赋值
            self.latencies.append(latency)
            print(f"Latency collected: {latency} ms")  # 添加日志以确保每次请求的结果都被正确收集

    def parse_tcping(self, latencies):
        result = ""
        self.result_dict["host_ip"] = self.host  # 使用输入的host作为host_ip
        self.result_dict["tcping_detail"] = result
        self.result_dict["code"] = self.result_code
        if self.result_dict["host_ip"]=="" and self.ip_type==6:
            self.result_dict["host_ip"] = "::"

        if latencies:
            self.result_dict["min_latency"] =int(round(min(latencies), 0))  # 格式化最小延迟为小数点后两位
            self.result_dict["max_latency"] = int(round(max(latencies), 0) ) # 格式化最大延迟为小数点后两位
            self.result_dict["avg_latency"] = int(round(statistics.mean(latencies), 0) ) # 格式化平均延迟为小数点后两位
            self.result_dict["packet_loss_rate"] = (latencies.count(0.0) / len(latencies)) * 100
            self.result_dict["jitter"] = int(round(statistics.stdev(latencies), 0)) if len(latencies) > 1 else 0.0  # 格式化抖动为小数点后两位

        if len(self.result_dict["host_ip"]) > 0:
            ip_finder_obj = ip_utils.ip_finder("nettest_ipaddress.db", "respone_relation.txt")
            self.result_dict["ip_info"] = ip_finder_obj.find_main_ip(self.result_dict["host_ip"])
        print("tcping result:", self.result_dict)

if __name__ == '__main__':
    this = os.path.abspath(os.path.dirname(__file__))
    module = os.path.split(this)[0]
    print('sys.path.append("%s")' % module)
    sys.path.append(module)
    for i, val in enumerate(sys.path):
        print("[%s] %s" % (i + 1, val))

    print('参数个数为:', len(sys.argv), '个参数。')
    print('参数列表:', str(sys.argv))
    print('脚本名:', str(sys.argv[0]))

    print('__file__:', __file__)
    print('sys.executable:', sys.executable)
    print('sys.argv[0]:', sys.argv[0])
    print('os.getcwd():', os.getcwd())
    print('sys.frozen:', getattr(sys, 'frozen', False))
    print('sys._MEIPASS:', getattr(sys, '_MEIPASS', None))
    host = sys.argv[2]
    outfile = sys.argv[1]
    port = sys.argv[3]
    ip_type = int(sys.argv[4])
    dnsserver = ""
    if len(sys.argv) > 4:
        dnsserver = sys.argv[5]
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    tcping_obj = Probe_Tcping(host, outfile, port, ip_type,dnserver=dnsserver)
    asyncio.run(tcping_obj.run_tcping())