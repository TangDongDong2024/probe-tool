import math
from urllib.parse import urlparse

import ip_utils
import logging


def get_host_from_url(input_str):
    try:
        parsed_url = urlparse(input_str)
        hostname = parsed_url.hostname
        return hostname
    except ValueError:
        logging.error("Invalid URL")
        return None

def truncate_url(url, max_length=128):
    if len(url) <= max_length:
        return url
    half_length = (max_length - 6) // 2
    start = url[:half_length]
    end = url[-half_length:]
    return f"{start}......{end}"

def init_result_info(result_info, task_list):
    if len(task_list) > 0:
        first_task = task_list[0]
        result_info["result_main"] = {
            "url_main": first_task["url"],
            "time_dns": 0,
            "time_tcp": 0,
            "time_ssl": 0,
            "time_ttfb": 0,
            "time_total": 0,
            "time_first_page": 0,
            "time_first_screen": 0,
            "time_full_page": 0,
            "time_total_test": 0,
            "host_ip": "",
            "content_type": "",
            "http_code": 0,
            "error_code": 0,
            "redirect_count":0,
            "open_is_success":0,
            "speed_first_page": 0,
            "speed_full_page": 0,
            "total_size": 0,
            "total_request_num": 0,
            "request_loaded_num": 0,
            "request_loaded_rate": 0,
            "ip_operator": "",
            "ip_province": "",
            "ip_city": "",
            "ip_bsbw_count": 0,
            "ip_bsws_count": 0,
            "ip_yw_count": 0,
            "ip_qt_count": 0,
            "ip_null_count": 0,
            "ip_all_count": 0
        }
        result_info["result_suburl"] = []
        return True
    return False

def process_one_result(result,result_dict):

    result_dict["result_suburl"].append(result)
    result_dict["result_main"]["total_size"] += result["size_download"]
    if result["index"] == 0:
        result_dict["result_main"]["time_dns"] = result["time_namelookup"]
        result_dict["result_main"]["time_tcp"] = result["time_connect"]
        result_dict["result_main"]["time_ssl"] = result["time_appconnect"]
        result_dict["result_main"]["time_ttfb"] = result["time_starttransfer"] - result["time_pretransfer"] if result["time_starttransfer"] > result["time_pretransfer"] else 0.0
        result_dict["result_main"]["time_total"] = result["time_total"]
        result_dict["result_main"]["host_ip"] = result["primary_ip"]
        result_dict["result_main"]["http_code"] = result["http_code"]
        result_dict["result_main"]["execute_code"] = result["execute_code"]
        result_dict["result_main"]["error_message"] = result["error_message"]
        result_dict["result_main"]["content_type"] = result["content_type"]
        result_dict["result_main"]["effective_url"] = result["effective_url"]
        result_dict["result_main"]["redirect_count"] = result["redirect_count"]
        if result["size_download"] > 0:
            result_dict["result_main"]["speed_first_page"] = (result["speed_download"]) / 1024
        else:
            result_dict["result_main"]["speed_first_page"] = 0
        result_dict["result_main"]["time_first_page"] = 1000.0 * (result["time_end"] - result_dict["start_time"])
        result_dict["result_main"]["min_body"] = result["min_body"]
def update_result_statistics(result_dict):
    success_count = 0
    for result_suburl in result_dict["result_suburl"]:
        if result_suburl["success"] == 1:
            success_count += 1

    total_request = len(result_dict["result_suburl"])
    success_rate = success_count / total_request
    result_dict["result_main"]["total_request_num"] = total_request
    result_dict["result_main"]["request_loaded_num"] = success_count
    result_dict["result_main"]["request_loaded_rate"] = success_rate * 100.0
    result_dict["result_main"]["time_total_test"] = 1000.0 * (result_dict["end_time"] - result_dict["start_time"])
def fill_ip_info_fast(result_info):
    ip_finder_obj = ip_utils.ip_finder("./nettest_ipaddress.db", "respone_relation.txt")
    for item in result_info["result_suburl"]:
        if len(item["primary_ip"]) > 0:
            item["ip_group"] = ""
            item["ip_operator"] = ""
            item["ip_province"] = ""
            item["ip_city"] = ""
            item["time_start"] = 1000.0 * (item["time_start"] - result_info["start_time"])
            item["time_end"] = 1000.0 * (item["time_end"] - result_info["start_time"])

    ip_main = result_info["result_main"]["host_ip"]
    ip_main_info = ip_finder_obj.find_main_ip(ip_main)
    result_info["result_main"]["ip_operator"] = ip_main_info["ip_operator"]
    result_info["result_main"]["ip_province"] = ip_main_info["ip_province"]
    result_info["result_main"]["ip_city"] = ip_main_info["ip_city"]
    result_info["result_main"]["ip_bwbs_count"] = 0
    result_info["result_main"]["ip_bwws_count"] = 0
    result_info["result_main"]["ip_yw_count"] = 0
    result_info["result_main"]["ip_qt_count"] = 0
    result_info["result_main"]["ip_null_count"] = 0
    result_info["result_main"]["ip_all_count"] = 0

def fill_ip_info(result_info):
    ip_finder_obj = ip_utils.ip_finder("./nettest_ipaddress.db", "respone_relation.txt")
    dict_ip_count = ip_finder_obj.init_dict_ip_count()
    for item in result_info["result_suburl"]:
        if len(item["primary_ip"]) > 0:
            ip_group = ip_finder_obj.count_ip(item["primary_ip"], item["http_code"], dict_ip_count)
            item["ip_group"] = ip_group["ip_group"]
            item["ip_operator"] = ip_group["ip_operator"]
            item["ip_province"] = ip_group["ip_province"]
            item["ip_city"] = ip_group["ip_city"]
            item["time_start"] = 1000.0 * (item["time_start"] - result_info["start_time"])
            item["time_end"] = 1000.0 * (item["time_end"] - result_info["start_time"])

    ip_main = result_info["result_main"]["host_ip"]
    ip_main_info = ip_finder_obj.find_main_ip(ip_main)
    result_info["result_main"]["ip_operator"] = ip_main_info["ip_operator"]
    result_info["result_main"]["ip_province"] = ip_main_info["ip_province"]
    result_info["result_main"]["ip_city"] = ip_main_info["ip_city"]
    result_info["result_main"]["ip_bwbs_count"] = dict_ip_count["本网本省"]
    result_info["result_main"]["ip_bwws_count"] = dict_ip_count["本网外省"]
    result_info["result_main"]["ip_yw_count"] = dict_ip_count["异网"]
    result_info["result_main"]["ip_qt_count"] = dict_ip_count["其他"]
    result_info["result_main"]["ip_null_count"] = dict_ip_count["空"]
    result_info["result_main"]["ip_all_count"] = dict_ip_count["总量"]

def check_success(result_info,ip_type):
    execute_code = result_info["result_main"]["execute_code"]
    http_code = result_info["result_main"]["http_code"]
    if execute_code == 0:
        if result_info["result_main"]["http_code"] > 199 and result_info["result_main"]["http_code"] < 400:
            result_info["result_main"]["open_is_success"] = 1
        else:
            result_info["result_main"]["open_is_success"] = 0
        result_info["result_main"]["error_code"] = 0
    else:
        if execute_code == 3:
            result_info["result_main"]["error_code"] = 1008
        elif execute_code == 6:
            result_info["result_main"]["error_code"] = 1001
            if ip_type == 4:
                result_info["result_main"]["host_ip"] = "0.0.0.0"
            elif ip_type == 6:
                result_info["result_main"]["host_ip"] = "::"
        elif execute_code == 7:
            result_info["result_main"]["error_code"] = 1002
        elif execute_code == 28:
            if result_info["result_main"]["time_total"] >= 7000:
                result_info["result_main"]["error_code"] = 1006
            else:
                error_message = result_info["result_main"]["error_message"]
                if error_message.startswith("Connection timed out"):
                    result_info["result_main"]["error_code"] = 1002
                elif error_message.startswith("Failed to connect to"):
                    result_info["result_main"]["error_code"] = 1002
                elif error_message.startswith("Operation too slow"):
                    result_info["result_main"]["error_code"] = 1005
                elif error_message.startswith("Operation timed out"):
                    result_info["result_main"]["error_code"] = 1005
                elif error_message.startswith("Resolving timed out"):
                    result_info["result_main"]["error_code"]= 1001
                    if ip_type == 4:
                        result_info["result_main"]["host_ip"] = "0.0.0.0"
                    elif ip_type == 6:
                        result_info["result_main"]["host_ip"] = "::"
                else:
                    result_info["result_main"]["error_code"] = 1099
        elif execute_code == 35:
            result_info["result_main"]["error_code"] = 1003
        elif execute_code == 47:
            result_info["result_main"]["error_code"] = 1007
        elif execute_code == 52:
            result_info["result_main"]["error_code"] = 1005
        elif execute_code == 56:
            result_info["result_main"]["error_code"] = 1004
        else:
            result_info["result_main"]["error_code"] = 1099

        if http_code in [0, -1]:
            result_info["result_main"]["http_code"] = result_info["result_main"]["error_code"]

        if http_code > 199 and http_code < 400:
            result_info["result_main"]["open_is_success"] = 1

def calc_suburl_metrics(result_dict):
    index_full = -1
    if "result_suburl" in result_dict:
        index_full = len(result_dict["result_suburl"]) - 1
    if index_full > -1:
        success_list = []
        for subItem in result_dict["result_suburl"]:
            logging.debug(f"suburl:{subItem['url']}")
            temp_url = subItem["url"]
            subItem["url"] = truncate_url(temp_url, 128)
            if subItem["http_code"] == 200 and subItem["execute_code"] == 0 and subItem["time_total"] < 5000 and subItem["time_namelookup"] < 5000:
                success_list.append(subItem)
        sorted(success_list, key=lambda i: i['time_end'])
        sorted(result_dict["result_suburl"], key=lambda i: i['time_end'])
        if index_full > 99:
            index_full = 99
        succes_list_max_index = len(success_list)
        if succes_list_max_index > 0:
            succes_list_max_index = succes_list_max_index - 1
        index_pp90 = math.floor(0.9 * index_full)
        index_succes_90 = math.floor(0.9 * succes_list_max_index)
        if index_pp90 < succes_list_max_index:
            index_succes_90 = index_pp90
        if len(success_list) > 0:
            result_dict["result_main"]["time_first_screen"] = 1000.0 * (success_list[index_succes_90]["time_end"] - result_dict["start_time"])
            result_dict["result_main"]["time_full_page"] = 1000.0 * (success_list[succes_list_max_index]["time_end"] - result_dict["start_time"])
            result_dict["result_main"]["speed_full_page"] = (result_dict["result_main"]["total_size"] / (result_dict["end_time"] - result_dict["start_time"])) / 1024
        else:
            if result_dict["result_main"]["total_size"] > 0:
                result_dict["result_main"]["speed_full_page"] = (result_dict["result_main"]["total_size"] / (result_dict["end_time"] - result_dict["start_time"])) / 1024

def check_body_block(result_dict):
    body = result_dict["result_main"]["min_body"]
    if "警方提示疑似诈骗" in body:
        logging.debug("警方提示疑似诈骗")
        result_dict["result_main"]["open_is_success"] = 0
        result_dict["result_main"]["http_code"] = 1009
        result_dict["result_main"]["error_code"] = 1009

def check_jump_block(result_dict,ip_type):
    if result_dict["result_main"]["redirect_count"]>0:
        effective_host = get_host_from_url(result_dict["result_main"]["effective_url"])
        if effective_host in ["0.0.0.0", "127.0.0.1", '::1', '::', '::0', 'FE80::1']:
            result_dict["result_main"]["open_is_success"] = 0
            result_dict["result_main"]["dns_block"] = 1
            result_dict["result_main"]["error_code"] = 1010
            result_dict["result_main"]["http_code"] = 1010
        else:
            if result_dict["result_main"]["error_code"] > 0:
                if result_dict["result_main"]["http_code"] != 200:
                    result_dict["result_main"]["open_is_success"] = 0
                if result_dict["result_main"]["error_code"] == 1001:
                    if ip_type == 4:
                        result_dict["result_main"]["host_ip"] = "0.0.0.0"
                    elif ip_type == 6:
                        result_dict["result_main"]["host_ip"] = "::"
            else:
                if result_dict["result_main"]["http_code"] != 200:
                    result_dict["result_main"]["http_code"] = 301
    if result_dict["result_main"]["host_ip"] in ["183.252.183.98", "183.252.183.9", "182.43.124.6", "2409:8034:3830:42::4"]:
        result_dict["result_main"]["open_is_success"] = 0
        result_dict["result_main"]["dns_block"] = 1
        result_dict["result_main"]["http_code"] = 1009
        result_dict["result_main"]["error_code"] = 1009