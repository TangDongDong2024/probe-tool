import asyncio
import ipaddress
import socket
import concurrent.futures
import random
import wmi
# import winloop
import pythoncom
from probe_dns_block import DNSServer
from icmplib import async_ping
# from pythonping import ping
from scapy.all import *
from scapy.layers.inet import IP,ICMP
from scapy.layers.inet6 import IPv6,ICMPv6EchoRequest
import argparse
import time
import statistics
import ip_utils
import json
import paho.mqtt.client as mqtt


def test():
    pythoncom.CoInitialize()

    c = wmi.WMI()


    pythoncom.CoUninitialize()
def trace_hops(target_ip, max_hops=30, timeout=1, batch_size=10):
    packets = []
    results = []
    batch_results = []

    for ttl in range(1, max_hops + 1):
        packet_id = random.randint(1, 65535)
        if ':' in target_ip:
            packet = IPv6(dst=target_ip, hlim=ttl) / ICMPv6EchoRequest(id=packet_id)
        else:
            packet = IP(dst=target_ip, ttl=ttl, id=packet_id) / ICMP(id=packet_id)
        packets.append(packet)

        if len(packets) >= batch_size or ttl == max_hops:
            answered, unanswered = sr(packets, timeout=timeout, verbose=0, multi=True)
            for one in answered:
                answer = one.answer
                query = one.query
                cost_time = (answer.time - query.time) * 1000
                ttl = query.hlim if query.name == "IPv6" else one.query.ttl
                ip = one.answer.src
                batch_results.append((ttl, ip, cost_time))
            packets = []

    results.extend(batch_results)
    return results


def trace_single_hop(target_ip, ttl, timeout=2):
    packet_id = random.randint(1, 65535)  # 生成一个随机的ID
    if ':' in target_ip:  # 判断是否为IPv6地址
        packet = IPv6(dst=target_ip, hlim=ttl) / ICMPv6EchoRequest(id=packet_id)
    else:
        packet = IP(dst=target_ip, ttl=ttl, id=packet_id) / ICMP(id=packet_id)  # 设置包的ID

    start_time = time.time()  # 记录开始时间
    response= sr1(packet, timeout=timeout, verbose=0)
    end_time = time.time()  # 记录结束时间

    if response is not None:
        time_taken = (end_time - start_time) * 1000  # 计算往返时间
        return ttl, response.src, time_taken
    return ttl, None, None



async def ping_nr_task(nr, ip, count=10, interval=0.3, timeout=1, iptype=4):
    if ':' in ip:  # 判断是否为IPv6地址
        iptype = 6
    else:
        iptype = 4
    time_start_ping=time.time()
    ttl=255
    result = await async_ping(ip, count=count, interval=interval, timeout=timeout, family=iptype)
    # result = ping(ip, count=count, interval=interval, timeout=timeout, family=iptype)
    cost_time = (time.time()-time_start_ping ) * 1000
    print(f"Ping results for {nr}: {ip} costtime:{cost_time}\n{result}")
    return nr, result
async def fast_ping(ip_nr_dict, iptype=4,batch_size=20):
    tasks = []
    iptype = 4

    result_dict={}
    # 分批处理任务
    for i in range(0, len(ip_nr_dict), batch_size):
        batch = list(ip_nr_dict.items())[i:i + batch_size]
        tasks.extend(asyncio.create_task(ping_nr_task(nr, ip, count=10, interval=0.3, timeout=1, iptype=iptype)) for nr, ip in batch)

        try:
            print(f"Starting ping tasks for batch {i // batch_size + 1}...")
            results = await asyncio.wait_for(asyncio.gather(*(tasks)), timeout=15)
        except asyncio.TimeoutError:
            print("Timeout occurred while waiting for ping tasks to complete.")
            results = [task.result() for task in tasks if task.done() and not task.cancelled()]
        except asyncio.CancelledError:
            print("Ping tasks were cancelled.")
            results = [task.result() for task in tasks if task.done() and not task.cancelled()]
        
        for nr, result in results:  # 修改: 直接遍历 results 获取 (nr, result)
            result_dict[nr] = result
        
        # 清空任务列表，准备下一批任务
        tasks = []

    return result_dict
def ping_single_ip(ip, count=10, timeout=2):
    packet_id = random.randint(1, 65535)  # 生成一个随机的ID
    if ':' in ip:  # 判断是否为IPv6地址
        packet = IPv6(dst=ip) / ICMPv6EchoRequest(id=packet_id)
    else:
        packet = IP(dst=ip, id=packet_id) / ICMP(id=packet_id)  # 设置包的ID

    times = []
    for _ in range(count):
        start_time = time.time()  # 记录开始时间
        response = sr1(packet, timeout=timeout, verbose=0)
        end_time = time.time()  # 记录结束时间
        if response is not None:
            time_taken = (end_time - start_time) * 1000  # 计算往返时间
            times.append(time_taken)
        else:
            times.append(None)

    return times


def ping_ips_concurrent(ip_nr_dict, count=10, timeout=1, concurrency=4):
    """
    Perform concurrent ping tests on a list of IPs.

    :param ips: List of IPs to ping.
    :param count: Number of packets to send to each IP.
    :param timeout: Timeout for each ping.
    :param concurrency: Number of concurrent threads.
    """
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(ping_single_ip, ip, count, timeout): (nr, ip) for nr, ip in ip_nr_dict.items()}
        for future in concurrent.futures.as_completed(futures):
            nr, ip = futures[future]
            try:
                times = future.result()
                times = [t for t in times if t is not None]  # Remove None values (packet loss)
                if times:
                    min_time = min(times)
                    max_time = max(times)
                    avg_time = statistics.mean(times)
                    packet_loss_rate = (count - len(times)) / count * 100
                else:
                    min_time = None
                    max_time = None
                    avg_time = None
                    packet_loss_rate = 100
                results[nr] = {
                    "ip": ip,
                    "min_time": min_time,
                    "max_time": max_time,
                    "avg_time": avg_time,
                    "packet_loss_rate": packet_loss_rate
                }
                print(
                    f"Ping results for {ip}: min={min_time}ms, max={max_time}ms, avg={avg_time}ms, loss={packet_loss_rate}%")
            except Exception as e:
                results[nr] = {
                    "ip": ip,
                    "min_time": None,
                    "max_time": None,
                    "avg_time": None,
                    "packet_loss_rate": 100
                }
                print(f"Failed to ping {ip}: {e}")
    return results

async def get_destip(address:str,ip_type:int=4,local_dns_server:str=""):
    start_time = time.time()
    destip=""
    try:
        ipaddress.ip_address(address)
        destip=address
    except ValueError:
        localdnsservers=[]
        if len(local_dns_server)>0:
            localdnsservers.append(local_dns_server)
        dns_queryer = DNSServer(0.5, localdnsservers)
        time_dns_query = time.time()
        local_results = await dns_queryer.query(localdnsservers, address, ip_type)  # 使用await等待协程完成
        if local_results and len(local_results)>0:
            destip = local_results[0]
        else:
            destip="0.0.0.0"


    over_time = time.time()
    print("run time:{}", over_time - start_time)
    return destip
async def trace_route_concurrent(target, max_hops=30, timeout=1, concurrency=4, address_family=None, local_dns_server=""):
    """
    Perform a concurrent trace route to the target.

    :param target: The target host to trace.
    :param max_hops: Maximum number of hops to trace.
    :param timeout: Timeout for each hop.
    :param concurrency: Number of concurrent threads.
    :param address_family: Address family to use (socket.AF_INET for IPv4, socket.AF_INET6 for IPv6, or None for auto).
    """
    ip_type = 4
    if address_family == socket.AF_INET:
        ip_type = 4
    elif address_family == socket.AF_INET6:
        ip_type = 6
    else:
        ip_type = 0
    target_ip = await get_destip(target, ip_type=ip_type, local_dns_server=local_dns_server)
    if target_ip == "":
        print(f"无法解析目标地址 {target}")
        return []
    print(f"Tracing route to {target}({target_ip}) over a maximum of {max_hops} hops:")
    results = []
    results = trace_hops(target_ip, max_hops)
    # 对结果进行排序
    results.sort(key=lambda x: x[0])
    final_result = []
    for nr, ip, time in results:
        if ip is None:
            ip = "*"
        if time is None:
            time = -1
        final_result.append({"nr": nr, "ip": ip, "time": time})
        if ip != "*":
            print(f"  {nr}    {ip}    {time:.2f}ms")
        else:
            print(f"  {nr}    *")
        if ip == target_ip:
            break

    print(f"Trace complete.")
    return final_result

def is_internal_ip(ip):
    #  RFC 1918 定义，仅覆盖以下私有地址段：
    # 10.0.0.0/8
    # 172.16.0.0/12
    # 192.168.0.0/16
    # 运营商级 NAT 地址的特殊性
    # 100.64.0.0/10
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private:
            return True
        # 额外检查 100.64.0.0/10
        if ip.startswith("100."):
            return True
        return ip_obj in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False
def fill_ip_info(dest_ip):
    if len(dest_ip) > 0 and dest_ip != "*":
        ip_finder_obj = ip_utils.ip_finder("nettest_ipaddress.db", "respone_relation.txt")
        rn_ip_info = ip_finder_obj.find_main_ip(dest_ip)
        if rn_ip_info["ip_operator"] is None:
            rn_ip_info["ip_operator"] = ""
        if rn_ip_info["ip_province"] is None:
            rn_ip_info["ip_province"] = ""
        if rn_ip_info["ip_city"] is None:
            rn_ip_info["ip_city"] = ""
        line_ip_info = f"{rn_ip_info['ip_province']}{rn_ip_info['ip_city']}{rn_ip_info['ip_operator']}"
        if line_ip_info == "":
            line_ip_info = "未知"
        if is_internal_ip(dest_ip):
            line_ip_info = "其它"

        return line_ip_info
    else:
        return "未知"


def publish_mqtt_message(broker, port, topic, message):
    client = mqtt.Client()
    try:
        client.connect(broker, port)
        client.publish(topic, message)
        print(f"Message published to {topic} on broker {broker}")
    except Exception as e:
        print(f"Failed to publish message: {e}")
    finally:
        client.disconnect()


def print_result(tracer_result, ping_results=None):
    app_result = []
    if ping_results:
        for one_result in tracer_result:
            nr_result = {}
            nr_result["hop"] = one_result["nr"]
            nr_result["ip"] = one_result["ip"]
            nr_result["ip_info"] = fill_ip_info(one_result["ip"])
            nr_result["send"] = ""
            nr_result["recv"] = ""
            nr_result["loss"] = ""
            nr_result["min"] = ""
            nr_result["max"] = ""
            nr_result["avg"] = ""
            int_nr = int(one_result["nr"])
            if int_nr in ping_results:
                nr_ping_result = ping_results[int_nr]
                nr_result["send"] = f"{nr_ping_result['send']}" if nr_ping_result[
                                                                                   "send"] is not None else ""
                nr_result["recv"] = f"{nr_ping_result['recv']}" if nr_ping_result[
                                                                             "recv"] is not None else ""
                nr_result["loss"] = f"{nr_ping_result['packet_loss_rate']*100:.2f}" if nr_ping_result[
                                                                                   "packet_loss_rate"] is not None else ""
                nr_result["min"] = f"{nr_ping_result['min_time']:.2f}" if nr_ping_result["min_time"] is not None else ""
                nr_result["max"] = f"{nr_ping_result['max_time']:.2f}" if nr_ping_result["max_time"] is not None else ""
                nr_result["avg"] = f"{nr_ping_result['avg_time']:.2f}" if nr_ping_result["avg_time"] is not None else ""

            app_result.append(nr_result)
    else:
        for one_result in tracer_result:
            nr_result = {}
            nr_result["hop"] = one_result["nr"]
            nr_result["ip"] = one_result["ip"]
            nr_result["ip_info"] = ""
            nr_result["send"] = ""
            nr_result["recv"] = ""
            nr_result["loss"] = ""
            nr_result["min"] = ""
            nr_result["max"] = ""
            nr_result["avg"] = ""
            app_result.append(nr_result)
    app_result_str = json.dumps(app_result, ensure_ascii=False, indent=None)
    print(f"detail=\"{app_result_str}\"")

    return app_result_str


async def main():
    parser = argparse.ArgumentParser(description="Concurrent Traceroute Tool")
    parser.add_argument("target", help="Target host to trace")
    # parser.add_argument("--max-hops", type=int, default=30, help="Maximum number of hops")
    # parser.add_argument("--timeout", type=int, default=2, help="Timeout for each hop in seconds")
    # parser.add_argument("--concurrency", type=int, default=4, help="Number of concurrent threads")
    parser.add_argument("--address-family", choices=["ipv4", "ipv6"], help="Force address family (ipv4 or ipv6)")
    parser.add_argument("--mqtt-broker", default="192.168.5.227", help="MQTT broker address")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-topic", default="traceroute", help="MQTT topic to publish to")
    parser.add_argument("--task-id", default="391565447", help="任务id")
    parser.add_argument("--output-file", default="outputfile.json", help="任务id")
    parser.add_argument("--dnsserver", default="", help="DNS服务器IP")

    args = parser.parse_args()
    address_family = None
    iptype=4
    if args.address_family == "ipv4":
        address_family = socket.AF_INET
        iptype=4
    elif args.address_family == "ipv6":
        address_family = socket.AF_INET6
        iptype=6
    start_trace_time = time.time()  # 记录开始时间
    results = await trace_route_concurrent(args.target, address_family=address_family, concurrency=1, local_dns_server=args.dnsserver)

    end_trace_time = time.time()  # 记录结束时间
    print(f"Trace completed in {end_trace_time - start_trace_time:.2f} seconds.")
    print(results)
    task_id = args.task_id
    mqtt_broker = args.mqtt_broker
    mqtt_port = args.mqtt_port
    mqtt_topic = args.mqtt_topic
    outputfile = args.output_file
    first_result = print_result(results)
    mqtt_message = f"method=midtask;prior=2;taskid={task_id};testnum=2;result=\"{first_result}\""
    if mqtt_broker:
        publish_mqtt_message(mqtt_broker, mqtt_port, mqtt_topic, mqtt_message)
    ip_nr_dict = {}
    ip_nr_dict = {hops["nr"]: hops["ip"] for hops in results if hops["ip"] != "*"}
    start_ping_time = time.time()  # 记录开始时间
    # thread_ping_iplist(ip_nr_dict,count=10)
    ping_task_results = await fast_ping(ip_nr_dict,iptype=iptype)
    nr_results = {}

    for nr, ping_result in ping_task_results.items():
        nr_results[nr] = {
            "ip": ping_result.address,
            "min_time": ping_result.min_rtt,
            "max_time": ping_result.max_rtt,
            "avg_time": ping_result.avg_rtt,
            "packet_loss_rate": ping_result.packet_loss,
            "send": ping_result.packets_sent,
            "recv": ping_result.packets_received
        }

    end_ping_time = time.time()  # 记录开始时间
    print(f"Ping completed in {end_ping_time - start_ping_time:.2f} seconds.")
    # ping_results = ping_ips_concurrent(ip_nr_dict, concurrency=4)
    # print(ping_results)
    final_result = print_result(results, nr_results)
    # mqtt_message = f"method=fintask;prior=2;taskid={task_id};testnum=2;result=\"{first_result}\""
    # if mqtt_broker:
    #     publish_mqtt_message(mqtt_broker, mqtt_port, mqtt_topic, mqtt_message)

    # 写入final_result到文件
    with open(outputfile, "w", encoding="utf-8") as f:
        f.write(final_result)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())