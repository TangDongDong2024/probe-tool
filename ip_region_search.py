from xdbSearcher import XdbSearcher
class IPRegionSearch(object):
    def __init__(self, dbpath="./ip2region.xdb"):
        self.dbPath = dbpath
        self.cb = XdbSearcher.loadContentFromFile(dbfile=self.dbPath)

        # 2. 仅需要使用上面的全文件缓存创建查询对象, 不需要传源 xdb 文件
        self.searcher = XdbSearcher(contentBuff=self.cb)



    def __del__(self):
        self.searcher.close()
    def search(self, ip):
        try:
            region_str = self.searcher.search(ip)
            # 假设 region_str 的格式为 "国家|区域|省份|城市|ISP"
            parts = region_str.split('|')
            if len(parts) >= 5:
                # 提取省份、城市和ISP
                ip_province = parts[2]
                ip_city = parts[3]
                ip_operator = parts[4]
                return {'ip_operator': ip_operator, 'ip_province': ip_province, 'ip_city': ip_city}
            else:
                return {'ip_operator': "", 'ip_province': "", 'ip_city': ""}
        except Exception as e:
            return {'ip_operator': "", 'ip_province': "", 'ip_city': ""}



