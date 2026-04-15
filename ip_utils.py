
import sqlite3
import traceback
import json
import ipaddress
class ip_finder(object):

    def __del__(self):
        self.db_con.close()

    def __init__(self, db_file,local_network_file):
        self.db_name=db_file
        self.local_network_operator= self.load_json_file(local_network_file)
        self.db_con=self.load_ipaddress_db(self.db_name)

    def ip2int(self,ip: str) -> int:
        if ip[0]=='[' and ip[-1]==']':
            ip=ip[1:-1]
        return int(ipaddress.ip_address(ip))
        # return sum(int(v) * 256 ** (3 - i) for i, v in enumerate(ip.split(".")))

    # 加载IP库
    def load_ipaddress_db(self,db_name):
        conn=None
        try:
            # conn = sqlite3.connect (db_name)
            db_conn_uri="file:{}?mode=ro".format(db_name)
            conn=sqlite3.connect (db_name, uri=True)
        except BaseException as e:
            print (traceback.format_exc ())
        return conn

    # 加载探针的网络运营商信息
    def load_json_file(self,filename):
        dict_operator={"1":"移动","2":"联通","3":"电信"}
        local_ip_operator=""
        try:
            with open (filename, encoding='utf-8') as a:
                # 读取文件
                result_dict = json.load (a)
                if "NETWORK_TYPE" in result_dict:
                    operator_code=result_dict["NETWORK_TYPE"]
                    if operator_code in dict_operator:
                        local_ip_operator= dict_operator[operator_code]

        except BaseException as e:
            print (traceback.format_exc ())
        return local_ip_operator

    #  初始化统计数据模板
    def init_dict_ip_count(self):
        dict_ip_count={"ip_group":"","local_ip_operator":self.local_network_operator,"本网本省":0,"本网外省":0,"异网":0,"其他":0,"空":0,"总量":0}
        return dict_ip_count

    # 从CDN 的IP库查询IP归属信息
    def select_ip_from_cdn(self,str_ip):
        result_dict={"code":0,"ip_province":"","ip_city":"","ip_operator":""}
        if self.db_con is None:
            return result_dict
        if len(str_ip)<2:
            return result_dict
        if str_ip[0]=='[' and str_ip[-1]==']':
            str_ip=str_ip[1:-1]
        int_ip =int(ipaddress.ip_address(str_ip))
        # print("int_ip=",int_ip);
        # int_ip = self.ip2int (str_ip)
        sql = '''SELECT IP_PROVINCE, IP_CITY, IP_OPERATOR, IP_DEPARTMENT  FROM cmcc_cdn_ipaddress WHERE IP_INT_BEGIN<{0} and {0}<IP_INT_END  ORDER BY IP_INT_SUB ASC;'''.format (
            int_ip)
        cursor=None
        try:
            cursor = self.db_con.cursor ()
            cursor.execute (sql)
        except BaseException as e:
            print (traceback.format_exc ())
        else:
            # print('else... no error exception occur!')
            values = cursor.fetchall ()
            # values=[('福建省', '', '移动', '')]
            if len(values)>0:
                result_dict["code"] =len(values)
                result_dict["ip_province"]="福建省"
                result_dict["ip_city"]=""
                result_dict["ip_operator"]="移动"
                # print ("从CDN 的IP库查询IP归属信息:",result_dict)
        finally:
            # print ('finally...')
            cursor.close ()
        return result_dict

    def select_ipv6_from_ipaddress(self,str_ip):
        result_dict={"code":0,"ip_province":"","ip_city":"","ip_operator":""}
        if self.db_con is None:
            return result_dict
        if ":" not in str_ip:
            return False
        int_ip = int (ipaddress.ip_address (str_ip))
        # print ("int_ipv6=", int_ip);
        # int_ip = self.ip2int (str_ip)
        # print ("IP:{}-->{}", str_ip, int_ip)
        sql ='''
        select province,city,isp from ipv6_range_info where X'{ip_int:032X}' BETWEEN ip_start_num AND ip_end_num ORDER BY ip_num ASC;
        '''.format(ip_int=int_ip)
        try:
            cursor = self.db_con.cursor ()
            cursor.execute (sql)
            print(sql)
        except BaseException as e:
            print (traceback.format_exc ())
        else:
            # print('else... no error exception occur!')
            values = cursor.fetchall ()
            # values=[('福建省', '', '移动', '')]
            if len (values) > 0:
                result_dict["code"] = len (values)
                result_dict["ip_province"] = values[0][0]
                result_dict["ip_city"] = values[0][1]
                result_dict["ip_operator"] = values[0][2]
                # print ("从IP库查询归属信息:", result_dict)
        finally:
            cursor.close ()
        return result_dict

    # 从IP库查询归属信息
    def select_ip_from_ipaddress(self,str_ip):
        result_dict={"code":0,"ip_province":"","ip_city":"","ip_operator":""}
        if self.db_con is None:
            return result_dict
        if str_ip[0]=='[' and str_ip[-1]==']':# ipv6
            str_ip=str_ip[1:-1]
        int_ip =int(ipaddress.ip_address(str_ip))
        # print("int_ip=",int_ip);
        # int_ip = self.ip2int (str_ip)
        # print("IP:{}-->{}",str_ip,int_ip)
        sql = '''SELECT IP_PROVINCE, IP_CITY, IP_OPERATOR, IP_DEPARTMENT  FROM nettest_ipaddress WHERE IP_INT_BEGIN<{0} and {0}<IP_INT_END  ORDER BY IP_INT_SUB ASC;'''.format (
            int_ip)
        try:
            cursor = self.db_con.cursor ()
            cursor.execute (sql)
        except BaseException as e:
            print (traceback.format_exc ())
        else:
            # print('else... no error exception occur!')
            values = cursor.fetchall ()
            # values=[('福建省', '', '移动', '')]
            if len(values)>0:
                result_dict["code"] = len(values)
                result_dict["ip_province"]=values[0][0]
                result_dict["ip_city"]=values[0][1]
                result_dict["ip_operator"]=values[0][2]
                # print ("从IP库查询归属信息:", result_dict)
        finally:
            cursor.close ()
        return result_dict


    # 忽略3个条件的元素参与统计
    # ①子资源【资源归属地划分】为空的数据
    # ②子元素返回状态码为4或者5开头的元素数据
    # ③子元素返回状态码为0的元素数据
    def skip_count(self,httpcode,ip_group):
        if httpcode==0:
            return True
        elif str(httpcode).startswith("4") or str(httpcode).startswith("5"):
            return True
        if ip_group=="空":
            return True

        return False

    def find_main_ip(self,str_ip):
        main_ip_info = {"ip_operator": "", "ip_province": "", "ip_city": ""}
        if len(str_ip)==0:
            return main_ip_info
        if ":" in str_ip:
            result_dict = self.select_ipv6_from_ipaddress (str_ip)
            main_ip_info["ip_operator"] = result_dict["ip_operator"]
            main_ip_info["ip_province"] = result_dict["ip_province"]
            main_ip_info["ip_city"] = result_dict["ip_city"]
            return main_ip_info
        result_dict = self.select_ip_from_cdn (str_ip)
        if result_dict["code"] == 0:
            result_dict = self.select_ip_from_ipaddress (str_ip)
        main_ip_info["ip_operator"] = result_dict["ip_operator"]
        main_ip_info["ip_province"] = result_dict["ip_province"]
        main_ip_info["ip_city"] = result_dict["ip_city"]
        return main_ip_info

    # 查询并统计IP归属信息
    def count_ip(self,str_ip,http_code,dict_ip_count):
        result_dict=None
        if ":" not in str_ip:
            result_dict = self.select_ip_from_cdn (str_ip)
            if result_dict["code"] == 0:
                result_dict = self.select_ip_from_ipaddress ( str_ip)
        else:
            result_dict = self.select_ipv6_from_ipaddress (str_ip)

        ip_group={}
        ip_group["ip_group"]=""
        ip_group["ip_operator"] = result_dict["ip_operator"]
        ip_group["ip_province"] =result_dict["ip_province"]
        ip_group["ip_city"] = result_dict["ip_city"]

        if result_dict["ip_province"]=="":
            ip_group["ip_group"] ="空"
        elif result_dict["ip_operator"] == dict_ip_count["local_ip_operator"]:
            if result_dict["ip_province"]=="福建省":
                ip_group["ip_group"] = "本网本省"

            else:
                ip_group["ip_group"] = "本网外省"

        elif result_dict["ip_operator"] in ["电信","移动","联通"]:
            ip_group["ip_group"] ="异网"

        elif result_dict["ip_operator"] == "其他":
            ip_group["ip_group"] ="其他"


        if self.skip_count(http_code,ip_group["ip_group"] )==False:
            dict_ip_count[ip_group["ip_group"]]+=1
            dict_ip_count["总量"] += 1

        dict_ip_count["总量"]=dict_ip_count["总量"] -dict_ip_count["空"]
        return ip_group


# if __name__ == '__main__':
#     ip_finder_obj=ip_finder ("nettest_ipaddress.db","respone_relation.txt")
#     dict_ip_count= ip_finder_obj.init_dict_ip_count()
#     ip_group=ip_finder_obj.count_ip("183.250.188.58",200,dict_ip_count)
#     print("IP归属:{0},统计信息:{1}".format(ip_group,dict_ip_count))


