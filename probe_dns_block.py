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
    """
    DNS查询器类

    功能说明:
        封装异步DNS查询操作，支持指定DNS服务器进行域名解析。
        使用aiodns库实现异步查询，避免阻塞主线程。

    属性说明:
        timeout (float): DNS查询超时时间（秒）
        nameservers (list): DNS服务器列表
        resolver_obj (aiodns.DNSResolver): aiodns解析器实例
    """

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
        """
        异步查询域名解析结果

        参数说明:
            nameservers (list): DNS服务器列表
            domain (str): 要查询的域名
            ip_type (int): IP协议类型 - 4:IPv4, 6:IPv6, 0:两者都查

        返回值:
            list: 解析到的IP地址列表

        实现说明:
            - 使用aiodns异步查询，避免阻塞
            - 分别查询A记录（IPv4）和AAAA记录（IPv6）
        """
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
    """
    DNS封堵检测器类

    功能说明:
        通过对比本地DNS和公共DNS的解析结果，判断域名是否被DNS封堵。
        这是识别"域名可访问但被定向到封堵页面"场景的关键检测模块。

    封堵判定逻辑:
        1. 使用本地DNS（如运营商DNS）查询域名
        2. 使用公共DNS（如阿里DNS 223.5.5.5）查询同一域名
        3. 判定条件（同时满足）：
           - 本地DNS返回的IP全部为封堵IP
           - 公共DNS至少返回一个非封堵IP

    封堵IP黑名单:
        BLOCKED_IPS_v4: IPv4封堵IP列表
        BLOCKED_IPS_v6: IPv6封堵IP列表
    """

    CHINA_MOBILE_DNS = '211.138.151.161'
    GOOGLE_DNS = '8.8.8.8'
    ALI_DNS = '223.5.5.5'
    CNNIC_DNS='1.2.4.8'
    TENCENT_DNS = '183.60.83.19'
    BLOCKED_IPS_v4 = ['0.0.0.0', '127.0.0.1', '183.252.183.9', '183.252.183.98','182.43.124.6']
    BLOCKED_IPS_v6 = ['::1','::','::0','FE80::1','2409:8034:3830:42::4']

    def __init__(self,dnsserver:str=""):
        """
        初始化DNS封堵检测器

        参数说明:
            dnsserver (str): 指定使用的DNS服务器IP，为空则自动获取本机DNS
        """
        if dnsserver=="":
            self.local_dns_server=[]
        else:
            self.local_dns_server = [dnsserver]
    @staticmethod
    def is_valid_ip_address(address):
        """
        验证字符串是否为有效的IP地址

        返回值:
            bool: True表示是有效IP，False表示不是有效IP
        """
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False

    @staticmethod
    def parse_input(input_str):
        """
        解析URL或IP地址输入

        参数说明:
            input_str (str): 可以是完整URL、简单域名或IP地址

        返回值:
            tuple: (hostname, port, scheme, path)
        """
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
        """
        同步获取本机DNS服务器列表（Windows WMI）

        资源管理:
            使用try-finally确保COM库正确初始化和释放

        返回值:
            list: 有效的DNS服务器IP列表
        """
        # 初始化COM库
        pythoncom.CoInitialize()
        try:
            c = wmi.WMI()
            active_dns = []
            for interface in c.Win32_NetworkAdapterConfiguration(IPEnabled=True):
                if interface.DefaultIPGateway:  # 检查默认网关是否存在
                    dns_servers = interface.DNSServerSearchOrder
                    if dns_servers:
                        active_dns.extend(dns_servers)
        finally:
            pythoncom.CoUninitialize()  # 确保始终执行
        return active_dns

    async def check_dns_blocking(self, domain:str, iptype:int):
        """
        检测域名是否被DNS封堵

        功能说明:
            通过对比本地DNS和公共DNS的解析结果，判断域名是否被DNS层面的访问控制。

        参数说明:
            domain (str): 要检测的域名或URL
            iptype (int): IP协议类型 - 4:IPv4, 6:IPv6, 0:双栈

        返回值:
            tuple: (is_blocked, local_ips)
                - is_blocked (bool): True表示DNS封堵，False表示正常
                - local_ips (list): 本地DNS返回的IP列表

        封堵判定算法:
            1. 获取本地DNS服务器（如未指定则自动获取）
            2. 同时使用本地DNS和公共DNS查询目标域名
            3. 检查本地DNS返回的IP是否都是封堵IP
            4. 如果是封堵IP，检查公共DNS是否返回正常IP

        性能优化:
            - 本地DNS和公共DNS查询并行执行（asyncio.gather）
        """
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
        
        # ========== 优化1: 并行DNS查询 ==========
        time_dns_query = time.time()
        
        # 创建两个DNS查询器
        dns_queryer_local = DNSServer(0.5, self.local_dns_server)
        dns_queryer_public = DNSServer(0.5, public_dns_servers)
        
        # 并行执行两个DNS查询
        local_results, public_results = await asyncio.gather(
            dns_queryer_local.query(self.local_dns_server, hostname, iptype),
            dns_queryer_public.query(public_dns_servers, hostname, iptype)
        )
        
        print(f"DNS并行查询总耗时: {time.time() - time_dns_query}秒")
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
                for ip in public_results:
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
                for ip in public_results:
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
                for ip in public_results:
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

if __name__ == "__main__":
    """
    模块自测入口

    使用方法:
        python probe_dns_block.py

    测试内容:
        1. 测试DNSServer基本查询功能
        2. 测试DomainBlockChecker封堵检测功能
    """
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 将主逻辑封装到异步函数中
    async def main():
        localdnsservers = ["211.138.151.161"]
        dns_queryer = DNSServer(0.5, localdnsservers)
        time_dns_query = time.time()
        local_results = await dns_queryer.query(localdnsservers, "www.baidu.com", 4)
        print(f"本地DNS查询结果: {local_results}")
        print(f"本地DNS查询耗时: {time.time() - time_dns_query}秒")

        checker = DomainBlockChecker("")
        ret, localresult = await checker.check_dns_blocking("www.baidu.com", 4)
    # 使用 asyncio.run() 运行异步函数
    asyncio.run(main())
