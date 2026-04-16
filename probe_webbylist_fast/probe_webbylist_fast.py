# -*- coding: utf-8 -*-
"""
批量URL探测模块 (probe_webbylist_fast.py)
=====================================

功能描述:
    本模块提供批量网页探测功能，通过解析目标网页的HTML，
    获取页面引用的所有资源URL（JS、CSS、图片等），
    并模拟浏览器并发探测这些资源的可用性。

主要功能:
    1. HTML页面解析：提取页面所有资源链接
    2. DNS封堵检测：检测主域名是否被DNS封堵
    3. 批量资源探测：并发探测所有页面资源
    4. 性能统计：计算首屏时间、完整加载时间等
    5. IP归属地查询：识别目标服务器地理位置

性能特性:
    - DNS检查与HTML解析并行执行
    - 使用ThreadPoolExecutor并发探测资源
    - 使用CurlShare复用DNS缓存
    - CPU核心数+4个并发线程

输出指标:
    - time_first_page: 首页加载时间
    - time_first_screen: 首屏时间
    - time_full_page: 完整页面时间
    - speed_first_page: 首页下载速度
    - speed_full_page: 完整页面速度
    - open_is_success: 是否成功
    - error_code: 错误码

使用示例:
    ```bash
    python probe_webbylist_fast.exe -u https://example.com/ -o result.json -p 4
    ```

命令行参数:
    -u/--url: 目标URL（必填）
    -o/--output: 输出文件路径（默认performance_result.json）
    -p/--iptype: IP协议类型，4=IPv4，6=IPv6（默认4）
    -l/--log: 日志级别，debug/info/warning（默认debug）
    --dnsserver: 指定DNS服务器（可选）
"""

import argparse
import asyncio
import logging
import os
import multiprocessing
import concurrent.futures
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import json

import pycurl
from task_loader import load_task
from result_processor import init_result_info, fill_ip_info_fast, check_success, \
    calc_suburl_metrics, check_body_block, check_jump_block, update_result_statistics, process_one_result
from html_parser import get_list_from_html
from mylogger import MyLogger
from curl_request import CurlRequest
from probe_dns_block import DomainBlockChecker

def initialize_task_list(urls):
    """
    初始化任务列表

    参数说明:
        urls (list): URL列表

    返回值:
        list: 任务字典列表，每个元素包含url、index、referer

    实现说明:
        - index从0开始
        - referer为首个URL（用于首个请求）
        - 最多支持100个URL
    """
    task_list = []
    task_index = 0
    task = {}
    referer_url = ""
    for url in urls:
        task["url"] = url
        task["index"] = task_index
        if task_index == 0:
            referer_url = url
        task["referer"] = referer_url
        task_list.append(task.copy())
        task_index += 1
        if task_index > 99:
            g_log.debug("url数量超过100")
            break
    return task_list


def initialize_result_dict(task_list):
    """
    初始化结果字典

    参数说明:
        task_list (list): 任务列表

    返回值:
        dict: 包含任务列表和开始时间的结果字典
    """
    result_dict = {}
    init_result_info(result_dict, task_list)
    result_dict["start_time"] = time.time()
    return result_dict


def process_results(result_pool, result_dict):
    while not result_pool.empty():
        result = result_pool.get()
        result_pool.task_done()
        g_log.debug(f"save task_index:{result['index']}")
        process_one_result(result, result_dict)





def save_results(result_dict, outfile):
    with open(outfile, 'wb') as f:
        strjson = json.dumps(result_dict, ensure_ascii=False)
        json_bytes = strjson.encode('utf-8')
        f.write(json_bytes)


def curl_task(task_object, curl_object_pool: Queue, task_result_queue: Queue, G_CURL_SHARE):
    """
    执行单个curl探测任务

    参数说明:
        task_object (dict): 任务对象，包含url、index、referer
        curl_object_pool (Queue): curl对象池
        task_result_queue (Queue): 结果队列
        G_CURL_SHARE: curl共享对象（用于DNS缓存）

    返回值:
        dict: 探测结果
    """
    logger = logging.getLogger('curl_task')
    curl_object = None
    while True:
        try:
            if not curl_object_pool.empty():
                logger.debug(f"curl_object_pool.get() queue size:{curl_object_pool.qsize()}")
                curl_object = curl_object_pool.get(block=True, timeout=5)
                curl_object_pool.task_done()
                logger.debug(f"curl_object_pool.get() over queue size:{curl_object_pool.qsize()}")
                break
            else:
                logger.debug(f"empty queue size:{curl_object_pool.qsize()}")
                time.sleep(0.1)
                continue
        except Exception as e:
            logger.error(f'Error: curl_object_pool.get(). Error code: {e.args[0]}. Error message: {e.args[1]}')
    result_task = {}
    try:
        logger.debug("curl send_request start")
        curl_object.send_request(task_object["referer"], task_object["url"], task_object["index"], G_CURL_SHARE)
    except Exception as e:
        logger.error(f'Error: curl_object_pool.send_request(). Error code: {e.args[0]:d}. Error message: {e.args[1]}')
    try:
        result_task = curl_object.get_result()
    except Exception as e:
        logger.error(f'Error: curl_object_pool.get_result(). Error code: {e.args[0]}. Error message: {e.args[1]}')
    curl_object_pool.put(curl_object)
    try:
        task_result_queue.put(result_task.copy())
    except Exception as e:
        logger.error(f'Error: task_result_queue.put(). Error code: {e.args[0]}. Error message: {e.args[1]}')
    logger.debug(f"result_pool size:{task_result_queue.qsize()}, add result:{result_task['index']}")
    return result_task


def suburldown(tasklistfilename, outfile, isdnsblock, ip_type, localresult, dnsserver: str = "", g_log=None, total_timeout=10):
    """
    执行批量URL探测

    功能说明:
        1. 加载任务列表
        2. 创建curl连接池
        3. 并发执行所有URL探测
        4. 汇总结果并写入文件

    参数说明:
        tasklistfilename (str): 任务列表文件名
        outfile (str): 输出结果文件
        isdnsblock (bool): 是否DNS封堵
        ip_type (int): IP协议类型
        localresult (list): 本地DNS解析结果
        dnsserver (str): 指定DNS服务器
        g_log: 日志对象
        total_timeout (int): 总超时时间（秒）
    """
    global G_CURL_SHARE
    urls = load_task(tasklistfilename, g_log=g_log)
    task_list = initialize_task_list(urls)
    result_dict = initialize_result_dict(task_list)
    G_CURL_SHARE = CurlRequest.Init_Share_Curl()
    g_log.debug(G_CURL_SHARE)
    g_log.debug(f"tasklist:{str(task_list)}")
    poolsize = multiprocessing.cpu_count() + 4
    g_log.debug(f"当前机器CPU核心数为：{str(poolsize)}")
    result_pool = Queue()
    curl_pool = Queue(maxsize=poolsize)
    for i in range(poolsize):
        curl_pool.put(CurlRequest(ip_type, dns_server=dnsserver))
    g_log.debug(f"curl池队列数为：{curl_pool.qsize()}")
    with ThreadPoolExecutor(max_workers=poolsize) as executor:
        futures = []
        for task in task_list:
            future = executor.submit(curl_task, task, curl_pool, result_pool, G_CURL_SHARE)
            futures.append(future)
        start_time = time.time()
        for future in concurrent.futures.as_completed(futures):
            try:
                elapsed_time = time.time() - start_time
                if elapsed_time > total_timeout:
                    g_log.debug("Total timeout exceeded")
                    # 取消所有未完成的任务
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    break
                future.result(timeout=3)
            except TimeoutError:
                g_log.debug("future.result() Timeout exceeded error")

    result_dict["end_time"] = time.time()
    g_log.debug(f"cost:{result_dict['end_time'] - result_dict['start_time']:.3f} S")

    process_results(result_pool, result_dict)
    update_result_statistics(result_dict)

    if isdnsblock:
        result_dict["result_main"]["dns_block"] = 1
        result_dict["result_main"]["open_is_success"] = 0
        result_dict["result_main"]["error_code"] = 1011
        result_dict["result_main"]["http_code"] = 1011
    else:
        result_dict["result_main"]["dns_block"] = 0

    # 过滤封堵IP，查找有效的非封堵IP
    if result_dict["result_main"]["host_ip"] == "" and len(localresult) > 0:
        blocked_ips_v4 = ['0.0.0.0', '127.0.0.1', '183.252.183.9', '183.252.183.98', '182.43.124.6']
        blocked_ips_v6 = ['::1', '::', '::0', 'FE80::1', '2409:8034:3830:42::4']
        blocked_ips = blocked_ips_v6 if ip_type == 6 else blocked_ips_v4

        valid_ip_found = False
        for ip in localresult:
            # 跳过封堵IP
            if ip in blocked_ips:
                continue
            # 检查IP类型是否匹配
            if ip_type == 6 and ":" in ip:
                result_dict["result_main"]["host_ip"] = ip
                valid_ip_found = True
                break
            elif ip_type == 4 and "." in ip:
                result_dict["result_main"]["host_ip"] = ip
                valid_ip_found = True
                break

        # 如果没有找到有效IP，不设置默认值（让curl请求返回真实IP）
        if not valid_ip_found and ip_type == 4:
            result_dict["result_main"]["host_ip"] = "0.0.0.0"
        elif not valid_ip_found and ip_type == 6:
            result_dict["result_main"]["host_ip"] = "::"

    g_log.debug("check_error_code starting")
    check_success(result_dict,ip_type)
    check_jump_block(result_dict,ip_type)
    check_body_block(result_dict)
    if result_dict["result_main"]["open_is_success"] == 1:
        calc_suburl_metrics(result_dict)
    else:
        result_dict["result_main"]["time_first_page"] = 0
        result_dict["result_main"]["time_first_screen"] = 0
        result_dict["result_main"]["time_full_page"] = 0
        result_dict["result_main"]["speed_first_page"] = 0
        result_dict["result_main"]["speed_full_page"] = 0

    time_fill_ip_info_start = time.time()
    # if isfast:
    #     fill_ip_info_fast(result_dict)
    # else:
    #     fill_ip_info(result_dict)
    fill_ip_info_fast(result_dict)
    g_log.debug(f"fill_ip_info_cost:{time.time() - time_fill_ip_info_start:.3f}")

    save_results(result_dict, outfile)
    if G_CURL_SHARE:
        G_CURL_SHARE.close()


async def main(args, g_log):
    """
    主入口函数

    功能说明:
        1. 解析URL
        2. 并行执行DNS检查和HTML解析
        3. 调用suburldown执行批量探测
        4. 清理临时文件

    性能优化:
        - DNS检查与HTML解析并行执行
        - DNS查询采用asyncio并行查询
    """
    dns_server = args.dnsserver
    url_main = args.url
    # 新增URL协议头自动补全逻辑
    if not url_main.startswith(('http://', 'https://')):
        url_main = 'http://' + url_main
    
    # ========== 优化: 并行执行DNS检查和获取URL列表 ==========
    checker = DomainBlockChecker(dnsserver=dns_server)
    loop = asyncio.get_event_loop()
    
    # 使用线程池执行同步的 get_list_from_html
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    tasklistfilename = None
    isdnsblock = False
    localresult = []
    
    try:
        # 同时开始 DNS检查 和 获取URL列表
        dns_future = loop.create_task(checker.check_dns_blocking(url_main, ip_type))
        html_future = loop.run_in_executor(pool, get_list_from_html, url_main, dns_server)
        
        # 真正的并行等待：使用 asyncio.wait 同时等待两个任务
        done, pending = await asyncio.wait(
            [dns_future],
            timeout=30.0
        )
        
        # DNS检查完成或超时后，获取HTML结果
        # HTML通常需要更长时间，所以先等DNS
        try:
            # 等待HTML结果，给予合理的超时时间
            tasklistfilename = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(html_future)),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            g_log.error("获取URL列表超时")
            tasklistfilename = None
        except Exception as e:
            g_log.error(f"获取URL列表失败: {e}")
            tasklistfilename = None
        
        # 取消DNS检查（如果还在进行中）
        if not dns_future.done():
            dns_future.cancel()
            try:
                await dns_future
            except asyncio.CancelledError:
                pass
        
        # 获取DNS结果
        try:
            if dns_future.done() and not dns_future.cancelled():
                isdnsblock, localresult = dns_future.result()
        except asyncio.CancelledError:
            g_log.warning("DNS检查被取消")
        except Exception as e:
            g_log.error(f"DNS检查失败: {e}")
            isdnsblock, localresult = False, []
            
    except Exception as e:
        g_log.error(f"并行执行出错: {e}")
    finally:
        pool.shutdown(wait=False)

    g_log.debug(f"Current libcurl version: {pycurl.version}")
    
    # 如果获取URL列表失败，使用默认列表
    if tasklistfilename is None:
        g_log.error("无法获取URL列表，测试终止")
        g_log.close()
        return
    
    suburldown(tasklistfilename, str_out_file, isdnsblock, ip_type, localresult, dnsserver=dns_server, g_log=g_log)
    if os.path.exists(tasklistfilename):
        os.remove(tasklistfilename)
    g_log.debug("test over debug")
    g_log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="网页测试模拟仿真程序")
    parser.add_argument("-l", '--log', choices=['debug', 'info', 'warning'], default='debug', help="指定日志级别")
    parser.add_argument("-o", "--output", help="output file name", default="performance_result.json")
    parser.add_argument("-u", "--url", help="url", default="http://www.baidu.com")
    parser.add_argument("-p", "--iptype", help="ipv4 or ipv6", default="4")
    # parser.add_argument("-f", "--fast", help="fast", choices=['1', '0'], default="0")
    parser.add_argument("--dnsserver", help="dns server", default="")

    args = parser.parse_args()
    print("启动参数:", args)

    ip_type = int(args.iptype.upper())
    # fast_flag = int(args.fast.upper())
    tasklistfilename = "urllist.txt"
    isdnsblock = False
    localresult = []
    str_log_level = args.log.upper()
    str_out_file = args.output
    loglevel = getattr(logging, str_log_level, logging.INFO)
    g_log = MyLogger('probe_suburldown', level=loglevel, console=True, file_path='../logs/probe_suburldown.log')
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args, g_log))
