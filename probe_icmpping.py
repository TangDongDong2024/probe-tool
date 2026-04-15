import ipaddress
import sys
import os
import time
import json
import socket
import ip_utils

import asyncio



from icmplib import async_ping
# from icmplib import ICMPv4Socket, ICMPv6Socket, ICMPRequest
# from icmplib import ICMPLibError, ICMPError, TimeoutExceeded,exceptions
# from icmplib import PID, resolve, is_hostname, is_ipv6_address
from probe_dns_block import DNSServer

class Probe_Icmping(object):
    def __init__(self, host, out_file, send_num=10, pack_size=56, ip_type=4, timeout_per_request=0.5, total_timeout=10,dnserver:str=""):
        self.host = host
        self.out_file = out_file
        self.ip_type = ip_type
        self.request_count = send_num  # 修改参数名以匹配probe_ping.py
        self.timeout_per_request = timeout_per_request
        self.total_timeout = total_timeout
        self.local_dns_server = dnserver
        self.result_code = -1
        self.result_dict = {
            "code": -1,
            "host_ip": "0.0.0.0",
            "ip_info": {"ip_operator": "", "ip_province": "", "ip_city": ""},
            "drop_rate": -1,  # 修改字段名以匹配probe_ping.py
            "avg_jitter": -1,  # 修改字段名以匹配probe_ping.py
            "avg_rtt": -1,  # 修改字段名以匹配probe_ping.py
            "max_rtt": -1,  # 修改字段名以匹配probe_ping.py
            "min_rtt": -1,  # 修改字段名以匹配probe_ping.py
            "pack_size": pack_size,  # 添加pack_size字段
            "send_num": send_num  # 添加send_num字段
        }
        if ip_type == 6:
            self.result_dict["host_ip"] = "::"
        self.results=[]
        self.latencies = []
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
    async def run_icmping(self):
        start_time = time.time()
        try:
            # if self.is_valid_ip_address(self.host):
            #     self.host = self.host
            # else:
            #     # 解析主机名以支持IPv6
            #     self.host = socket.getaddrinfo(self.host, None, family=socket.AF_INET6 if self.ip_type == 6 else socket.AF_INET)[0][-1][0]
            await self.get_destip()
            tasks = [async_ping(self.host, count=self.request_count, interval=0, timeout=self.timeout_per_request, family=self.ip_type) for _ in range(1)]
            self.results = await asyncio.wait_for(asyncio.gather(*tasks), self.total_timeout)

        except socket.gaierror as e:
            print(f"Error resolving host: {e}")
            self.host = "0.0.0.0"  # 如果解析失败，保留原始host
            self.result_dict["code"] = -2
        except asyncio.TimeoutError:
            print("Total timeout exceeded")
            self.result_dict["code"] = -3  # 添加超时错误码
        over_time = time.time()
        print("run time:{}", over_time - start_time)

        if len(self.results)>0:
            self.parse_icmping(self.results[0])
        self.write_result_file()



    def parse_icmping(self, result):

        self.result_dict["host_ip"] = self.host
        # self.result_dict["tcping_detail"] = result
        self.result_dict["code"] = result.is_alive

        if result:
            self.result_dict["min_rtt"] = int(round(max(result.min_rtt, 0))) # 修改字段名以匹配probe_ping.py
            self.result_dict["max_rtt"] = int(round(max(result.max_rtt, 0)))# 修改字段名以匹配probe_ping.py
            self.result_dict["avg_rtt"] = int(round(result.avg_rtt, 0))  # 修改字段名以匹配probe_ping.py
            self.result_dict["drop_rate"] = round(result.packet_loss * 100)  # 修改字段名以匹配probe_ping.py
            self.result_dict["avg_jitter"] = int(round(result.jitter)) # 修改字段名以匹配probe_ping.py
        self.result_dict["success_count"] = result.packets_received  # 计算成功响应次数
        if len(self.result_dict["host_ip"]) > 0:
            ip_finder_obj = ip_utils.ip_finder("nettest_ipaddress.db", "respone_relation.txt")
            self.result_dict["ip_info"] = ip_finder_obj.find_main_ip(self.result_dict["host_ip"])
        print("icmping result:", self.result_dict)

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
    send_num = int(sys.argv[3])
    pack_size = int(sys.argv[4])
    ip_type = int(sys.argv[5])
    dnsserver = ""
    if len(sys.argv) > 6:
        dnsserver = sys.argv[6]

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    icmping_obj = Probe_Icmping(host=host, out_file=outfile, send_num=send_num, pack_size=pack_size, ip_type=ip_type,dnserver=dnsserver)
    asyncio.run(icmping_obj.run_icmping())