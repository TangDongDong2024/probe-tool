import time

import pycurl
import re
import ipaddress
import logging
from io import BytesIO

class CurlRequest(object):

    @staticmethod
    def Init_Share_Curl():
        CURL_SHARE = pycurl.CurlShare()
        CURL_SHARE.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_COOKIE)
        CURL_SHARE.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_DNS)
        CURL_SHARE.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_SSL_SESSION)
        return CURL_SHARE
    def __init__(self, ip_type:int=4,dns_server:str=""):
        self.CURLcode = 0
        self.ip_type = ip_type
        self.c = pycurl.Curl()
        self.buffer = BytesIO()
        self.local_dns_server=dns_server
        self.cookiesfile = "cookies.dat"
        self.performance_info = {
            "url": "",
            "time_total": -1,
            "time_namelookup": -1,
            "time_connect": -1,
            "time_appconnect": -1,
            "time_pretransfer": -1,
            "time_starttransfer": -1,
            "time_redirect": -1,
            "size_download": -1,
            "speed_download": -1,
            "size_upload": -1,
            "speed_upload": -1,
            "index": -1,
            "primary_ip": "",
            "effective_url": "",
            "http_code": -1,
            "execute_code": -1,
            "error_message": "",
            "time_start": -1,
            "time_end": -1,
            "success": -1,
            "content_type": "",
            "min_body": ""
        }
        self.logger = logging.getLogger('CurlRequest')

    def __del__(self):
        if self.c:
            self.c.close()

    def write_body(self, buf):
        body = buf
        if len(body) < 512:
            try:
                min_body = body.decode('utf-8', errors='replace')
                if min_body.isprintable():
                    self.performance_info["min_body"] = body.decode('utf-8', errors='replace')
                    self.logger.debug(f"write_body:{body}")
            except Exception as e:
                self.logger.error(f"write_body:{e}")

        return len(buf)

    def debug_function(self, curl_info, data):
        if curl_info == pycurl.INFOTYPE_TEXT:
            message = data.decode('utf-8')
            self.logger.debug(f"Debug Message: {message.strip()}")
            if '  Trying ' in message:
                ipv4_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
                ipv6_pattern = r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'
                ip_match = re.search(ipv4_pattern, message) or re.search(ipv6_pattern, message)
                if ip_match:
                    self.performance_info["primary_ip"] = ip_match.group(0)

    def set_curl_opt(self, request_url, referer_url,G_CURL_SHARE):
        try:
            self.buffer.truncate(0)
            self.logger.debug(f"set_curl_opt() start {self.ip_type}")
            self.c.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_V4 if self.ip_type == 4 else pycurl.IPRESOLVE_V6)
            if self.local_dns_server and self.local_dns_server!="":
                self.c.setopt(pycurl.DNS_SERVERS, self.local_dns_server)

            self.c.setopt(pycurl.URL, request_url)
            self.c.setopt(pycurl.WRITEDATA, self.buffer)
            self.c.setopt(pycurl.WRITEHEADER, self.buffer)
            self.c.setopt(pycurl.WRITEFUNCTION, self.write_body)
            self.c.setopt(pycurl.FOLLOWLOCATION, 1)
            self.c.setopt(pycurl.SSL_VERIFYPEER, 0)
            self.c.setopt(pycurl.SSL_VERIFYHOST, 0)
            self.c.setopt(pycurl.LOW_SPEED_LIMIT, 1)
            self.c.setopt(pycurl.LOW_SPEED_TIME, 5)
            self.c.setopt(pycurl.REFERER, referer_url)
            self.c.setopt(pycurl.AUTOREFERER, 1)
            self.c.setopt(pycurl.VERBOSE, 1)
            self.c.setopt(pycurl.DEBUGFUNCTION, self.debug_function)
            self.c.setopt(pycurl.CONNECTTIMEOUT, 5)
            self.c.setopt(pycurl.TIMEOUT, 7)
            self.c.setopt(pycurl.NOPROGRESS, 1)
            self.c.setopt(pycurl.FORBID_REUSE, 0)
            self.c.setopt(pycurl.FRESH_CONNECT, 0)
            self.c.setopt(pycurl.MAXREDIRS, 20)
            self.c.setopt(pycurl.TCP_KEEPALIVE, 0)
            self.c.setopt(pycurl.USERAGENT, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36')
            # Chrome标准请求头
            self.c.setopt(pycurl.HTTPHEADER, [
                'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding: gzip, deflate, br',
                'Connection: keep-alive',
                'Upgrade-Insecure-Requests: 1',
            ])
            if G_CURL_SHARE:
                try:
                    self.c.unsetopt(pycurl.SHARE)
                except Exception:
                    pass
                self.c.setopt(pycurl.SHARE, G_CURL_SHARE)
        except Exception as e:
            self.logger.error(f'Error message: {e}')
        self.logger.debug("set_curl_opt() end")

    def init_performance_info(self, request_url, index):
        self.logger.debug("init_performance_info() start")
        time_start = time.time()
        self.performance_info["url"] = request_url
        self.performance_info["index"] = index
        self.performance_info["time_start"] = time_start
        self.logger.debug("init_performance_info() end")

    def get_result(self):
        return self.performance_info

    def send_request(self, referer_url, request_url, index,G_CURL_SHARE):
        isip = False
        try:
            ipaddress.ip_address(referer_url)
            isip = True
        except ValueError:
            isip = False

        if not isip:
            self.set_curl_opt(request_url, referer_url,G_CURL_SHARE)
        self.init_performance_info(request_url, index)
        try:
            self.logger.debug("curl perform() start...")
            self.c.perform()
            self.performance_info["execute_code"] = 0
        except Exception as e:
            self.logger.error(f'Error: failed to perform curl.index:{index}. url:{request_url}. Error code: {e.args[0]}. Error message: {e.args[1]}')
            self.performance_info["execute_code"] = e.args[0]
            self.performance_info["error_message"] = e.args[1]
        time_end = time.time()
        self.performance_info["time_end"] = time_end
        self.getinfo()
        if self.performance_info["http_code"] > 199 and self.performance_info["http_code"] < 400:
            self.performance_info["success"] = 1
        self.logger.debug("curl perform() over")
        return self.performance_info["execute_code"]

    def getinfo(self):
        self.logger.debug("getinfo() start")
        self.logger.debug(f'self.performance_info["execute_code"]:{self.performance_info["execute_code"]}')
        # if self.performance_info["execute_code"] in [0, 7, 35, 28, 56]:
        if self.performance_info["execute_code"] >=0:
            try:
                self.performance_info["time_total"] = 1000.0 * self.c.getinfo(pycurl.TOTAL_TIME)
                self.performance_info["http_code"] = self.c.getinfo(pycurl.HTTP_CODE)
                bytes_content_type = self.c.getinfo_raw(pycurl.CONTENT_TYPE)
                if bytes_content_type is None:
                    bytes_content_type = b""
                str_content_type = bytes_content_type.decode(encoding="utf-8", errors="replace")
                self.logger.debug(f"content_type:{str_content_type}")
                redirect_count=self.c.getinfo(pycurl.REDIRECT_COUNT)
                self.performance_info["redirect_count"]= redirect_count
                self.logger.debug(f"redirect_count:{redirect_count}")
                self.performance_info["content_type"] = str_content_type
                self.performance_info["time_namelookup"] = 1000.0 * self.c.getinfo(pycurl.NAMELOOKUP_TIME)
                time_connect = 1000.0 * (self.c.getinfo(pycurl.CONNECT_TIME) - self.c.getinfo(pycurl.NAMELOOKUP_TIME))
                self.performance_info["time_connect"] = max(time_connect, 0.0)
                time_appconnect = 1000.0 * (self.c.getinfo(pycurl.APPCONNECT_TIME) - self.c.getinfo(pycurl.CONNECT_TIME))
                self.performance_info["time_appconnect"] = max(time_appconnect, 0.0)
                if self.performance_info["time_appconnect"] < 0:
                    self.performance_info["time_appconnect"] = 0
                self.performance_info["time_pretransfer"] = 1000.0 * self.c.getinfo(pycurl.PRETRANSFER_TIME)
                self.performance_info["time_starttransfer"] = 1000.0 * self.c.getinfo(pycurl.STARTTRANSFER_TIME)
                self.performance_info["time_redirect"] = 1000.0 * self.c.getinfo(pycurl.REDIRECT_TIME)
                self.performance_info["size_upload"] = self.c.getinfo(pycurl.SIZE_UPLOAD)
                self.performance_info["size_download"] = self.c.getinfo(pycurl.SIZE_DOWNLOAD)
                self.performance_info["speed_download"] = self.c.getinfo(pycurl.SPEED_DOWNLOAD)
                self.performance_info["speed_upload"] = self.c.getinfo(pycurl.SPEED_UPLOAD)
                if self.performance_info["http_code"]==200:
                    if self.c.getinfo(pycurl.PRIMARY_IP):
                        self.performance_info["primary_ip"] = self.c.getinfo(pycurl.PRIMARY_IP)
                self.performance_info["effective_url"] = self.c.getinfo(pycurl.EFFECTIVE_URL)
            except Exception as e:
                self.logger.error(f'Error: failed to curl Error code: {e.args[0]}. Error message: {e.args[1]}')
        self.logger.debug("getinfo() end")