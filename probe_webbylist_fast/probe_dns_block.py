import sys
import asyncio
import concurrent.futures
import aiodns
import ipaddress
import time
from urllib.parse import urlparse
import wmi
import pythoncom
class DNSServer:
    def __init__(self, timeout, nameservers=None):
        time_test = time.time()
        self.timeout = timeout
        self.nameservers = []
         # 移除手动创建的事件循环
        if nameservers is not None and isinstance(nameservers, list) and len(nameservers)>0:
            self.nameservers=nameservers
            self.resolver_obj = aiodns.DNSResolver(tries=1, nameservers=self.nameservers,timeout=self.timeout)
        else:
            self.resolver_obj = aiodns.DNSResolver(tries=1, timeout=self.timeout)

        print(f"DNS服务器: {self.resolver_obj.nameservers },初始化耗时: {time.time() - time_test}秒")

    async def query_async(self, nameservers, domain, ip_type=4):
        if nameservers is not None and isinstance(nameservers, list) and len(nameservers)>0:
            self.resolver_obj.nameservers = nameservers

        ip_addresses = []

        if ip_type in (0, 4):
            try:
                time_test = time.time()
                answers_a = await self.resolver_obj.query(domain, 'A')
                print(f"DNS服务器: DNS查询A耗时: {time.time() - time_test}秒")
                ip_addresses_a = [str(rdata.host) for rdata in answers_a]
                ip_addresses.extend(ip_addresses_a)
                print(f"DNS服务器: DNS查询A结果: {ip_addresses}")
            except aiodns.error.DNSError as e:
                print(f"DNS query failed: {e}")

        if ip_type in (0, 6):
            try:
                time_test = time.time()
                answers_aaaa = await self.resolver_obj.query(domain, 'AAAA')
                print(f"DNS服务器: DNS查询AAAA耗时: {time.time() - time_test}秒")
                ip_addresses_aaaa = [str(rdata.host) for rdata in answers_aaaa]
                ip_addresses.extend(ip_addresses_aaaa)
                print(f"DNS服务器: DNS查询AAAA结果: {ip_addresses_aaaa}")
            except aiodns.error.DNSError as e:
                print(f"DNS query failed: {e}")

        return ip_addresses

    def query(self, nameservers, domain, ip_type=4):
        return self.query_async(nameservers, domain, ip_type)  # 直接返回协程对象


class DomainBlockChecker:
    CHINA_MOBILE_DNS = '211.138.151.161'
    GOOGLE_DNS = '8.8.8.8'
    ALI_DNS = '223.5.5.5'
    CNNIC_DNS='1.2.4.8'
    TENCENT_DNS = '183.60.83.19'
    BLOCKED_IPS_v4 = ['0.0.0.0', '127.0.0.1', '183.252.183.9', '183.252.183.98','182.43.124.6']
    BLOCKED_IPS_v6 = ['::1','::','::0','FE80::1','2409:8034:3830:42::4']

    def __init__(self,dnsserver:str=""):
        if dnsserver=="":
            self.local_dns_server=[]
        else:
            self.local_dns_server = [dnsserver]
    @staticmethod
    def is_valid_ip_address(address):
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False

    @staticmethod
    def parse_input(input_str):
        if DomainBlockChecker.is_valid_ip_address(input_str) and ':' in input_str:
            # 如果hostname包含冒号且没有端口，则可能是IPv6地址
            if '[' not in input_str and ']' not in input_str:
                input_str = f"[{input_str}]"
        if not input_str.startswith(('http://', 'https://')):
            input_str = 'http://' + input_str
        try:
            parsed_url = urlparse(input_str)
            hostname = parsed_url.hostname
            port = parsed_url.port
            scheme = parsed_url.scheme or 'http'
        except ValueError:
            print("Invalid URL")
            return None, None, None, None

        if port is None:
            port = 443 if scheme == 'https' else 80

        path = parsed_url.path or '/'
        return hostname, port, scheme, path

    async def get_dns_via_wmi_async(self):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:

                active_dns = await asyncio.wait_for(
                    loop.run_in_executor(pool, self.get_dns_via_wmi_sync),
                    timeout=5  # 设置超时时间为2秒
                )
                return active_dns
            except asyncio.TimeoutError:
                print("get_dns_via_wmi_async timed out")
                return []


    def get_dns_via_wmi_sync(self):
        # 初始化COM库
        pythoncom.CoInitialize()
        c = wmi.WMI()
        active_dns = []
        for interface in c.Win32_NetworkAdapterConfiguration(IPEnabled=True):
            if interface.DefaultIPGateway:  # 检查默认网关是否存在
                dns_servers = interface.DNSServerSearchOrder
                if dns_servers:
                    active_dns.extend(dns_servers)

        pythoncom.CoUninitialize()
        return active_dns

    async def check_dns_blocking(self, domain:str, iptype:int):
        hostname, _, _, _ = self.parse_input(domain)
        if hostname is None:
            print("Invalid URL")
            return False, []
        if self.is_valid_ip_address(hostname):
            print(f"输入的是一个IP地址: {hostname}")
            return False, [hostname]
        time_start_get_dns_ip = time.time()
        if len(self.local_dns_server) == 0:
            self.local_dns_server = await self.get_dns_via_wmi_async()
        print(f"获取本地DNS服务器耗时: {time.time() - time_start_get_dns_ip}秒")
        public_dns_servers = [self.ALI_DNS]
        # local_results = DNSServer(self.CHINA_MOBILE_DNS).query_local(hostname)

        dns_queryer = DNSServer(0.5, self.local_dns_server)
        time_dns_query = time.time()
        local_results = await dns_queryer.query(self.local_dns_server, hostname, iptype)  # 使用await等待协程完成
        print(f"本地DNS查询耗时: {time.time() - time_dns_query}秒")
        # china_results = DNSServer(self.CHINA_MOBILE_DNS).query(hostname)
        dns_queryer2 = DNSServer(0.5, public_dns_servers)
        time_dns_query = time.time()
        google_results = await dns_queryer2.query(public_dns_servers, hostname, iptype)  # 使用await等待协程完成
        print(f"公共DNS查询耗时2: {time.time() - time_dns_query}秒")
        is_blocked_by_localdns = True
        all_not_in_blocked_ips = False
        if iptype == 4:
            if len(local_results) == 0:
                is_blocked_by_localdns = False
            for ip in local_results:
                if ip not in self.BLOCKED_IPS_v4:
                    is_blocked_by_localdns = False
                    break
            if is_blocked_by_localdns==True:
                for ip in google_results:
                    if ip not in self.BLOCKED_IPS_v4:
                        all_not_in_blocked_ips = True
                        break
        elif iptype == 6:
            if len(local_results) == 0:
                is_blocked_by_localdns = False
            for ip in local_results:
                if ip not in self.BLOCKED_IPS_v6:
                    is_blocked_by_localdns = False
                    break
                if is_blocked_by_localdns == True:
                    for ip in google_results:
                        if ip not in self.BLOCKED_IPS_v6:
                            all_not_in_blocked_ips = True
                            break
        else:
            for ip in local_results:
                if ":" in ip:
                    if ip not in self.BLOCKED_IPS_v6:
                        is_blocked_by_localdns = False
                        break
                else:
                    if ip not in self.BLOCKED_IPS_v4:
                        is_blocked_by_localdns = False
                        break
                if is_blocked_by_localdns == True:
                    for ip in google_results:
                        if ip not in self.BLOCKED_IPS_v6:
                            all_not_in_blocked_ips = True
                            break
                        if ip not in self.BLOCKED_IPS_v4:
                            all_not_in_blocked_ips = True
                            break
        if is_blocked_by_localdns==True and all_not_in_blocked_ips==True:
            is_block_flag=True
        else:
            is_block_flag=False
        # results_differ = set(local_results) != set(google_results)
        # is_block_flag = is_blocked_by_localdns and results_differ

        return is_block_flag, local_results