from scapy.all import *
import os
import sys
import random
import time

from scapy.layers.inet import ICMP, IP, TCP


def traceroute(destination, max_hops=30, timeout=0.5, num_packets=3):
    print(f"Tracing route to {destination} over a maximum of {max_hops} hops:\n")
    packets = []
    for ttl in range(1, max_hops + 1):
        responses = {}  # 存储每个包的发送时间和目标IP


        # 构造多个ICMP包（每个包有不同id/seq）
        for i in range(num_packets):
            icmp_id = random.randint(0, 65535)
            icmp_seq = ttl * num_packets + i
            packet = IP(dst=destination, ttl=ttl) / ICMP(type=8, code=0, id=icmp_id, seq=icmp_seq)
            packets.append(packet)
            responses[(icmp_id, icmp_seq)] = (packet, time.time())  # 记录发送时间

        # 批量发送所有包
    srloop(packets,)
    # ans, unans = sr(packets, timeout=10, verbose=0)
    # print(ans.summary())
        # 处理响应
        # reply_ips = []
        # for _, reply in ans:
        #     if reply.haslayer(ICMP):
        #         # 通过id/seq匹配请求包
        #         icmp_id_reply = reply[ICMP].id
        #         icmp_seq_reply = reply[ICMP].seq
        #         if (icmp_id_reply, icmp_seq_reply) in responses:
        #             sent_packet, sent_time = responses[(icmp_id_reply, icmp_seq_reply)]
        #             rtt = (time.time() - sent_time) * 1000  # 计算延迟（毫秒）
        #             reply_type = reply[ICMP].type
        #
        #             if reply_type == 11:  # Time Exceeded
        #                 reply_ips.append(f"{reply.src}  {rtt:.2f} ms")
        #             elif reply_type == 0:  # Echo Reply (目标到达)
        #                 reply_ips.append(f"{reply.src}  {rtt:.2f} ms")
        #                 return  # 结束追踪
        #
        # # 输出结果
        # output = f"{ttl}\t"
        # if len(reply_ips) > 0:
        #     # 合并相同IP的响应（如三个包都收到同一路由器的回复）
        #     unique_ips = {}
        #     for ip_rtt in reply_ips:
        #         ip, rtt = ip_rtt.split("  ")
        #         if ip not in unique_ips:
        #             unique_ips[ip] = []
        #         unique_ips[ip].append(rtt)
        #
        #     # 格式化为：IP 最短延迟/最长延迟/平均延迟
        #     for ip in unique_ips:
        #         rtts = [float(r.replace(" ms", "")) for r in unique_ips[ip]]
        #         output += f"{ip}  [{min(rtts):.2f}/{(sum(rtts) / len(rtts)):.2f}/{max(rtts):.2f}] ms\t"
        # else:
        #     output += "*\t*\t*"
        #
        # print(output)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: sudo python traceroute.py <destination>")
        sys.exit(1)

    destination = sys.argv[1]

    # traceroute(destination)
    # result, unans=traceroute(destination="www.deepseek.com", max_hops=30,  timeout=0.5, num_packets=3)
    # print(result)

    for pi in range(3):
        packets = []
        for i in range(1,11):
            start_ttl=pi*10
            current_ttl=start_ttl+i
            print(f"start_ttl:{start_ttl},current_ttl:{current_ttl}")
            packet_id = random.randint(1, 65535)  # 生成一个随机的ID
            packet = IP(dst=destination, ttl=current_ttl) / ICMP(type=8, code=0, id=packet_id)
            packets.append(packet)
        ans, unans = sr(packets,timeout=0.5, verbose=0,multi=True)
        for snd, rcv in ans:
            print(snd.ttl, rcv.src, isinstance(rcv.payload, TCP))
