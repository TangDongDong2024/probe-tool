import ipaddress
import sys
import os
import time
import json
import asyncio
import aiodns  # 修改: 添加aiodns库的导入
from probe_dns_block import DomainBlockChecker






class Probe_Dns(object):
    def __init__(self, dns_server, domain, out_file, request_count=10, timeout_per_request=1, total_timeout=60,  protocol_type=0):
        self.dns_server = dns_server
        self.domain = domain
        self.out_file = out_file
        self.request_count = request_count
        self.timeout_per_request = timeout_per_request
        self.total_timeout = total_timeout
        self.BLOCKED_IPS_v4 = ['0.0.0.0', '127.0.0.1', '183.252.183.9', '183.252.183.98', '182.43.124.6']
        self.BLOCKED_IPS_v6 = ['::1', '::', '::0', 'FE80::1', '2409:8034:3830:42::4']
        self.protocol_type = protocol_type  # 添加protocol_type属性
        self.result_code = -1
        self.result_dict = {
            "code": -1,
            "domain": domain,
            "target_ip": "",
            "request_count": request_count,
            "success_count": 0,
            "min_resolution_time": 0.0,
            "max_resolution_time": 0.0,
            "avg_resolution_time": 0.0,
            "resolution_success_rate": 0.0,
            "dnsblock":0,
        }
        self.resolutions = []
        self.write_result_file()

    def write_result_file(self):
        strjson = json.dumps(self.result_dict, ensure_ascii=False)
        with open(self.out_file, mode='w', encoding='utf-8') as f:
            f.write(strjson)

    async def check_dns_block(self, domain):
        checker = DomainBlockChecker()
        ret, localresult = await checker.check_dns_blocking(domain, self.protocol_type)  # 修改: 使用await调用异步方法
        if ret:
            self.result_dict["dnsblock"] = 1
        else:
            self.result_dict["dnsblock"] = 0

    async def run_dns_test(self):
        start_time = time.perf_counter()  # 使用time.perf_counter()提高时间精度
        tasks = [self.resolve_domain(i + 1) for i in range(self.request_count)]  # 创建所有任务
        semaphore = asyncio.Semaphore(1)  # 限制并发请求数量为5

        async def sem_task(task):
            async with semaphore:
                return await task

        sem_tasks = [asyncio.create_task(sem_task(task)) for task in tasks]  # 确保sem_tasks是Future对象
        try:
            await asyncio.wait_for(asyncio.gather(*sem_tasks), timeout=2)  # 并发执行任务，并设置总超时时间为2秒
        except asyncio.TimeoutError:
            print("DNS resolution timed out")
            self.result_dict["code"] = -2
            # 取消所有未完成的任务
            for task in sem_tasks:
                if not task.done():
                    task.cancel()
        except Exception as e:
            print(f"Error during DNS test: {e}")
            self.result_dict["code"] = -2
        over_time = time.perf_counter()  # 使用time.perf_counter()提高时间精度
        print("run time:{}", over_time - start_time)
        print("resolutions collected:", self.resolutions)
        self.result_code = 0 if any(self.resolutions) else -1
        print("returncode:", self.result_code)
        print("resolutions:", self.resolutions)
        self.result_dict["success_count"] = len([resolution for resolution in self.resolutions if resolution[0] is not None])
        await self.parse_dns_results(self.resolutions)  # 修改: 使用await调用异步方法
        if self.protocol_type ==4 and self.result_dict["target_ip"] in self.BLOCKED_IPS_v4:
            await self.check_dns_block(self.domain)
        elif self.protocol_type ==6 and self.result_dict["target_ip"] in self.BLOCKED_IPS_v6:
            await self.check_dns_block(self.domain)
        # else:
        #     self.result_dict["dnsblock"] = 0

        self.write_result_file()

    async def resolve_domain(self, request_index):  # 添加request_index参数
        resolver = aiodns.DNSResolver(servers=[self.dns_server])
        start = time.perf_counter()  # 使用time.perf_counter()提高时间精度
        try:
            if self.protocol_type == 0:
                # 并发查询AAAA和A记录
                aaaa_query = resolver.query(self.domain, 'AAAA')
                a_query = resolver.query(self.domain, 'A')
                try:
                    answers_a, answers_aaaa = await asyncio.gather(
                        asyncio.wait_for(a_query, timeout=self.timeout_per_request),
                        asyncio.wait_for(aaaa_query, timeout=self.timeout_per_request)
                    )
                    resolution_time = (time.perf_counter() - start) * 1000
                    resolution_time = round(resolution_time, 2)
                    for answer in answers_a:
                        target_ip = answer.host
                        self.resolutions.append((request_index, resolution_time, target_ip))  # 修改: 确保resolution_time是浮点数

                    for answer in answers_aaaa:
                        target_ip = answer.host
                        self.resolutions.append((request_index, resolution_time, target_ip))  # 修改: 确保resolution_time是浮点数
                    print(f"Request {request_index}: Resolution collected: {self.resolutions}")  # 使用request_index

                except aiodns.error.DNSError as e:
                    print(f"DNS query failed: {e}")
                    resolution_time = 0.0
                    # self.resolutions.append((request_index, resolution_time, None))  # 修改: 确保resolution_time是浮点数
                    print(f"Request {request_index}: Resolution collected: None in {resolution_time} ms")  # 使用request_index
            elif self.protocol_type == 4:
                # 查询A记录以支持IPv4
                a_query = resolver.query(self.domain, 'A')
                answers = await asyncio.wait_for(a_query, timeout=self.timeout_per_request)

                resolution_time = (time.perf_counter() - start) * 1000
                resolution_time = round(resolution_time, 2)
                for answer in answers:
                    target_ip = answer.host
                    self.resolutions.append((request_index, resolution_time, target_ip))  # 修改: 确保resolution_time是浮点数
                print(f"Request {request_index}: Resolution collected: {self.resolutions}")  # 使用request_index
            elif self.protocol_type == 6:
                # 尝试查询AAAA记录以支持IPv6
                aaaa_query = resolver.query(self.domain, 'AAAA')
                answers = await asyncio.wait_for(aaaa_query, timeout=self.timeout_per_request)
                resolution_time = (time.perf_counter() - start) * 1000
                resolution_time = round(resolution_time, 2)
                for answer in answers:
                    target_ip = answer.host
                    self.resolutions.append((request_index, resolution_time, target_ip))  # 修改: 确保resolution_time是浮点数
                print(f"Request {request_index}: Resolution collected: {self.resolutions}")  # 使用request_index
        except Exception as e:
            print(f"Error during resolution: {e}")
            resolution_time = 0.0
            # self.resolutions.append((request_index, resolution_time, None))  # 修改: 确保resolution_time是浮点数
            print(f"Request {request_index}: Resolution collected: None in {resolution_time} ms")  # 使用request_index

    async def parse_dns_results(self, resolutions):  # 修改: 将方法改为异步方法
        result = ""
        self.result_dict["code"] = self.result_code

        if resolutions:
            successful_resolutions = [resolution for resolution in resolutions if resolution[2] is not None]
            self.result_dict["target_ip"] = successful_resolutions[0][2] if successful_resolutions else ""
            self.result_dict["min_resolution_time"] = round(min(resolution[1] for resolution in resolutions))  # 修改: 四舍五入取整
            self.result_dict["max_resolution_time"] = round(max(resolution[1] for resolution in resolutions))  # 修改: 四舍五入取整
            self.result_dict["avg_resolution_time"] = round(sum(resolution[1] for resolution in resolutions) / len(resolutions))  # 修改: 四舍五入取整
            self.result_dict["resolution_success_rate"] = (len(successful_resolutions) / len(resolutions)) * 100
            
            # 添加所有成功解析的IP地址到结果字典
            self.result_dict["all_target_ips"] = list(set(resolution[2] for resolution in successful_resolutions))

            # 输出每次请求的响应信息
            for i, resolution in enumerate(resolutions):
                print(f"Request {resolution[0]}: Resolution collected: {resolution[2]} in {round(resolution[1])} ms ")  # 修改: 四舍五入取整


        print("dns test result:", self.result_dict)

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


    outfile = sys.argv[1]
    domain = sys.argv[2]
    dns_server = sys.argv[3]
    request_count = int(sys.argv[4])
    timeout_per_request = float(sys.argv[5])
    total_timeout = float(sys.argv[6])

    protocol_type = int(sys.argv[7])  # 添加对protocol_type参数的解析
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    dns_test_obj = Probe_Dns(dns_server, domain, outfile, request_count, timeout_per_request, total_timeout,  protocol_type)
    asyncio.run(dns_test_obj.run_dns_test())