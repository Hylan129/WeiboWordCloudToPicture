#微博抓取

#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import codecs
import copy
import csv
import json
import os
import random
import re
import sys
import traceback
from collections import OrderedDict
from datetime import date, datetime, timedelta
from time import sleep

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from tqdm import tqdm

# 提取关键微博信息
from wordcloud import WordCloud, STOPWORDS
from imageio import imread
import jieba

# 文本信息插入图片
from PIL import Image, ImageDraw, ImageFont
import time

class Weibo(object):
    def __init__(self, config):
        """Weibo类初始化"""
        self.validate_config(config)
        self.filter = config[
            'filter']  # 取值范围为0、1,程序默认值为0,代表要爬取用户的全部微博,1代表只爬取用户的原创微博
        since_date = str(config['since_date'])
        if since_date.isdigit():
            since_date = str(date.today() - timedelta(int(since_date)))
        self.since_date = since_date  # 起始时间，即爬取发布日期从该值到现在的微博，形式为yyyy-mm-dd
        self.write_mode = config[
            'write_mode']  # 结果信息保存类型，为list形式，可包含txt、csv、json、mongo和mysql五种类型
        self.pic_download = config[
            'pic_download']  # 取值范围为0、1,程序默认值为0,代表不下载微博原始图片,1代表下载
        self.video_download = config[
            'video_download']  # 取值范围为0、1,程序默认为0,代表不下载微博视频,1代表下载
        self.cookie = {'Cookie': config['cookie']}
        self.mysql_config = config.get('mysql_config')  # MySQL数据库连接配置，可以不填
        user_id_list = config['user_id_list']
        if not isinstance(user_id_list, list):
            if not os.path.isabs(user_id_list):
                user_id_list = os.path.split(
                    os.path.realpath(__file__))[0] + os.sep + user_id_list
            self.user_config_file_path = user_id_list  # 用户配置文件路径
            user_config_list = self.get_user_config_list(user_id_list)
        else:
            self.user_config_file_path = ''
            user_config_list = [{
                'user_uri': user_id,
                'since_date': self.since_date
            } for user_id in user_id_list]
            print(user_config_list)
        self.user_config_list = user_config_list  # 要爬取的微博用户的user_config列表
        self.user_config = {}  # 用户配置,包含用户id和since_date
        self.start_time = ''  # 获取用户第一条微博时的时间
        self.user = {}  # 存储爬取到的用户信息
        self.got_num = 0  # 存储爬取到的微博数
        self.weibo = []  # 存储爬取到的所有微博信息
        self.weibo_id_list = []  # 存储爬取到的所有微博id

    def validate_config(self, config):
        """验证配置是否正确"""

        # 验证filter、pic_download、video_download
        argument_lsit = ['filter', 'pic_download', 'video_download']
        for argument in argument_lsit:
            if config[argument] != 0 and config[argument] != 1:
                sys.exit(u'%s值应为0或1,请重新输入' % config[argument])

        # 验证since_date
        since_date = str(config['since_date'])
        if (not self.is_date(since_date)) and (not since_date.isdigit()):
            sys.exit(u'since_date值应为yyyy-mm-dd形式或整数,请重新输入')

        # 验证write_mode
        write_mode = ['txt', 'csv', 'json', 'mongo', 'mysql']
        if not isinstance(config['write_mode'], list):
            sys.exit(u'write_mode值应为list类型')
        for mode in config['write_mode']:
            if mode not in write_mode:
                sys.exit(
                    u'%s为无效模式，请从txt、csv、json、mongo和mysql中挑选一个或多个作为write_mode' %
                    mode)

        # 验证user_id_list
        user_id_list = config['user_id_list']
        if (not isinstance(user_id_list,
                           list)) and (not user_id_list.endswith('.txt')):
            sys.exit(u'user_id_list值应为list类型或txt文件路径')
        if not isinstance(user_id_list, list):
            if not os.path.isabs(user_id_list):
                user_id_list = os.path.split(
                    os.path.realpath(__file__))[0] + os.sep + user_id_list
            if not os.path.isfile(user_id_list):
                sys.exit(u'不存在%s文件' % user_id_list)

    def is_date(self, since_date):
        """判断日期格式是否正确"""
        try:
            if ':' in since_date:
                datetime.strptime(since_date, '%Y-%m-%d %H:%M')
            else:
                datetime.strptime(since_date, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def str_to_time(self, text):
        """将字符串转换成时间类型"""
        if ':' in text:
            result = datetime.strptime(text, '%Y-%m-%d %H:%M')
        else:
            result = datetime.strptime(text, '%Y-%m-%d')
        return result

    def handle_html(self, url):
        """处理html"""
        try:
            html = requests.get(url, cookies=self.cookie).content
            selector = etree.HTML(html)
            return selector
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def handle_garbled(self, info):
        """处理乱码"""
        try:
            info = (info.xpath('string(.)').replace(u'\u200b', '').encode(
                sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding))
            return info
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_nickname(self):
        """获取用户昵称"""
        try:
            url = 'https://weibo.cn/%s/info' % (self.user_config['user_id'])
            selector = self.handle_html(url)
            nickname = selector.xpath('//title/text()')[0]
            nickname = nickname[:-3]
            if nickname == u'登录 - 新' or nickname == u'新浪':
                self.write_log()
                sys.exit(u'cookie错误或已过期,请按照README中方法重新获取')
            return nickname
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_user_id(self, selector):
        """获取用户id，使用者输入的user_id不一定是正确的，可能是个性域名等，需要获取真正的user_id"""
        self.user_config['user_id'] = self.user_config['user_uri']
        url_list = selector.xpath("//div[@class='u']//a")
        for url in url_list:
            if (url.xpath('string(.)')) == u'资料':
                if url.xpath('@href') and url.xpath('@href')[0].endswith(
                        '/info'):
                    link = url.xpath('@href')[0]
                    self.user_config['user_id'] = link[1:-5]
                    break
        return self.user_config['user_id']

    def get_user_info(self, selector):
        """获取用户id、昵称、微博数、关注数、粉丝数"""
        try:
            self.user['id'] = self.get_user_id(selector)
            self.user['nickname'] = self.get_nickname()  # 获取用户昵称
            user_info = selector.xpath("//div[@class='tip2']/*/text()")
            weibo_num = int(user_info[0][3:-1])
            following = int(user_info[1][3:-1])
            followers = int(user_info[2][3:-1])
            self.user['weibo_num'] = weibo_num
            self.user['following'] = following
            self.user['followers'] = followers
            self.print_user_info()
            print('*' * 100)
            return self.user
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_page_num(self, selector):
        """获取微博总页数"""
        try:
            if selector.xpath("//input[@name='mp']") == []:
                page_num = 1
            else:
                page_num = (int)(
                    selector.xpath("//input[@name='mp']")[0].attrib['value'])
            return page_num
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_long_weibo(self, weibo_link):
        """获取长原创微博"""
        try:
            for i in range(5):
                selector = self.handle_html(weibo_link)
                if selector is not None:
                    info = selector.xpath("//div[@class='c']")[1]
                    wb_content = self.handle_garbled(info)
                    wb_time = info.xpath("//span[@class='ct']/text()")[0]
                    weibo_content = wb_content[wb_content.find(':') +
                                               1:wb_content.rfind(wb_time)]
                    if weibo_content is not None:
                        return weibo_content
                sleep(random.randint(6, 10))
        except Exception as e:
            return u'网络出错'
            print('Error: ', e)
            traceback.print_exc()

    def get_original_weibo(self, info, weibo_id):
        """获取原创微博"""
        try:
            weibo_content = self.handle_garbled(info)
            weibo_content = weibo_content[:weibo_content.rfind(u'赞')]
            a_text = info.xpath('div//a/text()')
            if u'全文' in a_text:
                weibo_link = 'https://weibo.cn/comment/' + weibo_id
                wb_content = self.get_long_weibo(weibo_link)
                if wb_content:
                    weibo_content = wb_content
            return weibo_content
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_long_retweet(self, weibo_link):
        """获取长转发微博"""
        try:
            wb_content = self.get_long_weibo(weibo_link)
            weibo_content = wb_content[:wb_content.rfind(u'原文转发')]
            return weibo_content
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_retweet(self, info, weibo_id):
        """获取转发微博"""
        try:
            weibo_content = self.handle_garbled(info)
            weibo_content = weibo_content[weibo_content.find(':') +
                                          1:weibo_content.rfind(u'赞')]
            weibo_content = weibo_content[:weibo_content.rfind(u'赞')]
            a_text = info.xpath('div//a/text()')
            if u'全文' in a_text:
                weibo_link = 'https://weibo.cn/comment/' + weibo_id
                wb_content = self.get_long_retweet(weibo_link)
                if wb_content:
                    weibo_content = wb_content
            retweet_reason = self.handle_garbled(info.xpath('div')[-1])
            retweet_reason = retweet_reason[:retweet_reason.rindex(u'赞')]
            original_user = info.xpath("div/span[@class='cmt']/a/text()")
            if original_user:
                original_user = original_user[0]
                weibo_content = (retweet_reason + '\n' + u'原始用户: ' +
                                 original_user + '\n' + u'转发内容: ' +
                                 weibo_content)
            else:
                weibo_content = (retweet_reason + '\n' + u'转发内容: ' +
                                 weibo_content)
            return weibo_content
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def is_original(self, info):
        """判断微博是否为原创微博"""
        is_original = info.xpath("div/span[@class='cmt']")
        if len(is_original) > 3:
            return False
        else:
            return True

    def get_weibo_content(self, info, is_original):
        """获取微博内容"""
        try:
            weibo_id = info.xpath('@id')[0][2:]
            if is_original:
                weibo_content = self.get_original_weibo(info, weibo_id)
            else:
                weibo_content = self.get_retweet(info, weibo_id)
            return weibo_content
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_publish_place(self, info):
        """获取微博发布位置"""
        try:
            div_first = info.xpath('div')[0]
            a_list = div_first.xpath('a')
            publish_place = u'无'
            for a in a_list:
                if ('place.weibo.com' in a.xpath('@href')[0]
                        and a.xpath('text()')[0] == u'显示地图'):
                    weibo_a = div_first.xpath("span[@class='ctt']/a")
                    if len(weibo_a) >= 1:
                        publish_place = weibo_a[-1]
                        if (u'视频' == div_first.xpath(
                                "span[@class='ctt']/a/text()")[-1][-2:]):
                            if len(weibo_a) >= 2:
                                publish_place = weibo_a[-2]
                            else:
                                publish_place = u'无'
                        publish_place = self.handle_garbled(publish_place)
                        break
            return publish_place
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_publish_time(self, info):
        """获取微博发布时间"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = self.handle_garbled(str_time[0])
            publish_time = str_time.split(u'来自')[0]
            if u'刚刚' in publish_time:
                publish_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            elif u'分钟' in publish_time:
                minute = publish_time[:publish_time.find(u'分钟')]
                minute = timedelta(minutes=int(minute))
                publish_time = (datetime.now() -
                                minute).strftime('%Y-%m-%d %H:%M')
            elif u'今天' in publish_time:
                today = datetime.now().strftime('%Y-%m-%d')
                time = publish_time[3:]
                publish_time = today + ' ' + time
                if len(publish_time) > 16:
                    publish_time = publish_time[:16]
            elif u'月' in publish_time:
                year = datetime.now().strftime('%Y')
                month = publish_time[0:2]
                day = publish_time[3:5]
                time = publish_time[7:12]
                publish_time = year + '-' + month + '-' + day + ' ' + time
            else:
                publish_time = publish_time[:16]
            return publish_time
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def print_user_info(self):
        """打印微博用户信息"""
        print(u'用户昵称: %s' % self.user['nickname'])
        print(u'用户id: %s' % self.user['id'])
        print(u'微博数: %d' % self.user['weibo_num'])
        print(u'关注数: %d' % self.user['following'])
        print(u'粉丝数: %d' % self.user['followers'])
        print(u'url：https://weibo.cn/%s' % self.user['id'])
        
    def get_publish_tool(self, info):
        """获取微博发布工具"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = self.handle_garbled(str_time[0])
            if len(str_time.split(u'来自')) > 1:
                publish_tool = str_time.split(u'来自')[1]
            else:
                publish_tool = u'无'
            return publish_tool
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_weibo_footer(self, info):
        """获取微博点赞数、转发数、评论数"""
        try:
            footer = {}
            pattern = r'\d+'
            str_footer = info.xpath('div')[-1]
            str_footer = self.handle_garbled(str_footer)
            str_footer = str_footer[str_footer.rfind(u'赞'):]
            weibo_footer = re.findall(pattern, str_footer, re.M)

            up_num = int(weibo_footer[0])
            footer['up_num'] = up_num

            retweet_num = int(weibo_footer[1])
            footer['retweet_num'] = retweet_num

            comment_num = int(weibo_footer[2])
            footer['comment_num'] = comment_num
            return footer
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_picture_urls(self, info, is_original):
        """获取微博原始图片url"""
        try:
            weibo_id = info.xpath('@id')[0][2:]
            picture_urls = {}
            if is_original:
                original_pictures = self.extract_picture_urls(info, weibo_id)
                picture_urls['original_pictures'] = original_pictures
                if not self.filter:
                    picture_urls['retweet_pictures'] = u'无'
            else:
                retweet_url = info.xpath("div/a[@class='cc']/@href")[0]
                retweet_id = retweet_url.split('/')[-1].split('?')[0]
                retweet_pictures = self.extract_picture_urls(info, retweet_id)
                picture_urls['retweet_pictures'] = retweet_pictures
                a_list = info.xpath('div[last()]/a/@href')
                original_picture = u'无'
                for a in a_list:
                    if a.endswith(('.gif', '.jpeg', '.jpg', '.png')):
                        original_picture = a
                        break
                picture_urls['original_pictures'] = original_picture
            return picture_urls
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()
        
    def get_one_weibo(self, info):
        """获取一条微博的全部信息"""
        try:
            weibo = OrderedDict()
            is_original = self.is_original(info)
            if (not self.filter) or is_original:
                weibo['id'] = info.xpath('@id')[0][2:]
                weibo['content'] = self.get_weibo_content(info,
                                                          is_original)  # 微博内容
                
                weibo['publish_place'] = self.get_publish_place(info)  # 微博发布位置
                weibo['publish_time'] = self.get_publish_time(info)  # 微博发布时间
                weibo['publish_tool'] = self.get_publish_tool(info)  # 微博发布工具
                footer = self.get_weibo_footer(info)
                weibo['up_num'] = footer['up_num']  # 微博点赞数
                weibo['retweet_num'] = footer['retweet_num']  # 转发数
                weibo['comment_num'] = footer['comment_num']  # 评论数
            else:
                weibo = None
            return weibo
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def is_pinned_weibo(self, info):
        """判断微博是否为置顶微博"""
        kt = info.xpath(".//span[@class='kt']/text()")
        if kt and kt[0] == u'置顶':
            return True
        else:
            return False

    def get_one_page(self, page):
        """获取第page页的全部微博"""
        try:
            url = 'https://weibo.cn/%s/profile?page=%d' % (
                self.user_config['user_uri'], page)
            selector = self.handle_html(url)
            info = selector.xpath("//div[@class='c']")
            is_exist = info[0].xpath("div/span[@class='ctt']")
            if is_exist:
                for i in range(0, len(info) - 2):
                    weibo = self.get_one_weibo(info[i])
                    if weibo:
                        if weibo['id'] in self.weibo_id_list:
                            continue
                        publish_time = self.str_to_time(weibo['publish_time'])
                        since_date = self.str_to_time(
                            self.user_config['since_date'])
                        if publish_time < since_date:
                            if self.is_pinned_weibo(info[i]):
                                continue
                            else:
                                """
                                print(u'{}已获取{}({})的第{}页微博{}'.format(
                                    '-' * 30, self.user['nickname'],
                                    self.user['id'], page, '-' * 30))
                                """
                                return True
                        #self.print_one_weibo(weibo)
                        self.weibo.append(weibo)
                        self.weibo_id_list.append(weibo['id'])
                        self.got_num += 1
                        #print('-' * 100)
            """
            print(u'{}已获取{}({})的第{}页微博{}'.format('-' * 30,
                                                 self.user['nickname'],
                                                 self.user['id'], page,
                                                 '-' * 30))
             """
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_filepath(self, type):
        """获取结果文件路径"""
        try:
            
            file_dir = self.user['nickname']
            os.system('mkdir '+ file_dir )
            file_path = file_dir + os.sep + self.user_config[
                'user_id'] + '.' + type
            return file_path
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def write_log(self):
        """当程序因cookie过期停止运行时，将相关信息写入log.txt"""
        file_dir = os.path.split(
            os.path.realpath(__file__))[0] + os.sep + 'weibo' + os.sep
        if not os.path.isdir(file_dir):
            os.makedirs(file_dir)
        file_path = file_dir + 'log.txt'
        content = u'cookie已过期，从%s到今天的微博获取失败，请重新设置cookie\n' % self.since_date
        with open(file_path, 'ab') as f:
            f.write(content.encode(sys.stdout.encoding))

    def write_csv(self, wrote_num):
        """将爬取的信息写入csv文件"""
        try:
            result_headers = [
                '微博id',
                '微博正文',
                '原始图片url',
                '微博视频url',
                '发布位置',
                '发布时间',
                '发布工具',
                '点赞数',
                '转发数',
                '评论数',
            ]
            if not self.filter:
                result_headers.insert(3, '被转发微博原始图片url')
                result_headers.insert(4, '是否为原创微博')
            result_data = [w.values() for w in self.weibo[wrote_num:]]
            if sys.version < '3':  # python2.x
                reload(sys)
                sys.setdefaultencoding('utf-8')
                with open(self.get_filepath('csv'), 'ab') as f:
                    f.write(codecs.BOM_UTF8)
                    writer = csv.writer(f)
                    if wrote_num == 0:
                        writer.writerows([result_headers])
                    writer.writerows(result_data)
            else:  # python3.x
                with open(self.get_filepath('csv'),
                          'a',
                          encoding='utf-8-sig',
                          newline='') as f:
                    writer = csv.writer(f)
                    if wrote_num == 0:
                        writer.writerows([result_headers])
                    writer.writerows(result_data)
            print(u'%d条微博写入csv文件完毕,保存路径:' % self.got_num)
            print(self.get_filepath('csv'))
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def update_user_config_file(self, user_config_file_path):
        """更新用户配置文件"""
        with open(user_config_file_path, 'rb') as f:
            lines = f.read().splitlines()
            lines = [line.decode('utf-8-sig') for line in lines]
            for i, line in enumerate(lines):
                info = line.split(' ')
                if len(info) > 0 and info[0].isdigit():
                    if self.user_config['user_uri'] == info[0]:
                        if len(info) == 1:
                            info.append(self.user['nickname'])
                            info.append(self.start_time)
                        if len(info) == 2:
                            info.append(self.start_time)
                        if len(info) > 3 and self.is_date(info[2] + ' ' +
                                                          info[3]):
                            del info[3]
                        if len(info) > 2:
                            info[2] = self.start_time
                        lines[i] = ' '.join(info)
                        break
        with codecs.open(user_config_file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def write_data(self, wrote_num):
        """将爬取到的信息写入文件或数据库"""
        if self.got_num > wrote_num:
            if 'csv' in self.write_mode:
                self.write_csv(wrote_num)

    def get_weibo_info(self):
        """获取微博信息"""
        try:
            url = 'https://weibo.cn/%s/profile' % (self.user_config['user_uri'])
            selector = self.handle_html(url)
            self.get_user_info(selector)  # 获取用户昵称、微博数、关注数、粉丝数
            #page_num = self.get_page_num(selector)  # 获取微博总页数
            page_num = 21
            wrote_num = 0
            page1 = 0
            random_pages = random.randint(1, 5)
            self.start_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            #for page in tqdm(range(1, page_num + 1), desc='Progress'):
            for page in range(1, page_num + 1):
                is_end = self.get_one_page(page)  # 获取第page页的全部微博
                if is_end:
                    break

                if page % 20 == 0:  # 每爬20页写入一次文件
                    self.write_data(wrote_num)
                    wrote_num = self.got_num

                # 通过加入随机等待避免被限制。爬虫速度过快容易被系统限制(一段时间后限
                # 制会自动解除)，加入随机等待模拟人的操作，可降低被系统限制的风险。默
                # 认是每爬取1到5页随机等待6到10秒，如果仍然被限，可适当增加sleep时间
                if (page - page1) % random_pages == 0 and page < page_num:
                    sleep(random.randint(6, 10))
                    page1 = page
                    random_pages = random.randint(1, 5)
                print("Finshed Deal Page：" + str(page) + '/'+ str(page_num))

            self.write_data(wrote_num)  # 将剩余不足20页的微博写入文件
            if not self.filter:
                print(u'共爬取' + str(self.got_num) + u'条微博')
            else:
                print(u'共爬取' + str(self.got_num) + u'条原创微博')
    
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_user_config_list(self, file_name):
        """获取文件中的微博id信息"""
        with open(file_name, 'rb') as f:
            try:
                lines = f.read().splitlines()
                lines = [line.decode('utf-8-sig') for line in lines]
            except UnicodeDecodeError:
                sys.exit(u'%s文件应为utf-8编码，请先将文件编码转为utf-8再运行程序' % file_name)
            user_config_list = []
            for line in lines:
                info = line.split(' ')
                if len(info) > 0 and info[0].isdigit():
                    user_config = {}
                    user_config['user_uri'] = info[0]
                    if len(info) > 2 and self.is_date(info[2]):
                        if len(info) > 3 and self.is_date(info[2] + ' ' +
                                                          info[3]):
                            user_config['since_date'] = info[2] + ' ' + info[3]
                        else:
                            user_config['since_date'] = info[2]
                    else:
                        user_config['since_date'] = self.since_date
                    user_config_list.append(user_config)
        return user_config_list

    def initialize_info(self, user_config):
        """初始化爬虫信息"""
        self.got_num = 0
        self.weibo = []
        self.user = {}
        self.user_config = user_config
        self.weibo_id_list = []

    def start(self):
        """运行爬虫"""
        try:
            for user_config in self.user_config_list:
                self.initialize_info(user_config)
                print('*' * 100)
                self.get_weibo_info()
                print(u'信息抓取完毕')
                print('*' * 100)
                if self.user_config_file_path:
                    self.update_user_config_file(self.user_config_file_path)
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()


def main(weiboid,days):
    try:
        config = {
    "user_id_list": [weiboid],
    "filter": 1,
    "since_date": days,
    "write_mode": ["csv"],
    "pic_download": 0,
    "video_download": 0,
    "cookie":"_T_WM=70422221270; SCF=AuNWQq_E4fCpWGT9E8bsLNOMjQJNRlPCKdVNNeSfC4FfiEavNL_03aElZYrES3FGpC8y0ELMOUF_-LIk5tAdlek.; SSOLoginState=1582189615; SUB=_2A25zSjx_DeRhGedG41UV8SvFzz6IHXVQtUQ3rDV6PUJbkdANLUX-kW1NUROaXHgNQd0l3AimFXdj3us0g9pVh-sM; SUHB=0sqw45sWuJWbEX"
}
        wb = Weibo(config)
        wb.start()  # 爬取微博信息
        return wb.user['nickname']
    except Exception as e:
        print('Error: ', e)
        traceback.print_exc()
        
def update_stops(path = 'stopwords.txt'):
    stop_set = [i.strip() for i in open(path).read().split('\n') if i !='']
    for i in stop_set:
        STOPWORDS.add(i)
    return STOPWORDS
        
def get_texts(path,siglelinenumber,displaylines):
    cur_time = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    all_contents1,all_contents2 = csv.reader(open(path,'r')),csv.reader(open(path,'r'))
    display_contents = [(content[1].strip(),content[3],content[7]) for content in all_contents1 if content[7]!='点赞数']
    cloud_contents = " ".join(jieba.cut(''.join([content[1].strip() for content in all_contents2])))
    
    display_content = sorted(display_contents,key =lambda x:int(x[2]),reverse =True)[0:3]
    display_content_new = ''
    n = siglelinenumber
    for i in display_content:
        if len(i[0]) < displaylines*n+1:
            display_content_new  += i[1] + '   ' + i[2] + ' stars\n' + '\n'.join([i[0][k:k + n] for k in range(0, len(i[0]), n)]) + '\n'*3
        else:
            display_content_new  += i[1] + '   ' + i[2] + ' stars\n' + '\n'.join([i[0][k:k + n] for k in range(0, (displaylines-1)*n, n)]) +'\n' + i[0][(displaylines-1)*n:(displaylines-1)*n+20]+'.....'+ '\n'*3
    
    return cloud_contents,'-'*24 + u'近日原创点赞热门' + '-'*24 + '\n'*3 + display_content_new + '-'*15 + cur_time + ' By Hylan129' + '-'*15

def cloud_pic(cloud_contents,max_words=150,backgroud_pic_path=r'run.png'):
    wc = WordCloud(stopwords= update_stops(), max_words= max_words, collocations=False, 
               background_color="RGB(20,255,155)", 
               font_path='/System/Library/Fonts/STHeiti Light.ttc', random_state=42, 
               mask=imread(backgroud_pic_path,pilmode="RGB"))
    wc.generate(cloud_contents)
    wc.to_file("ciyun_run.png")

#生成空白照片
def pic_blank(name):
    img = Image.new('RGB', (1080, 1920), (20, 255, 155))
    img.save(name +'.png')
    return name + '.png'

def pic_display(pic_file,position,headers,font_size):

    image = Image.open(pic_file)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    # 设置字体样式
    font_type = '/System/Library/Fonts/STHeiti Light.ttc'
    font = ImageFont.truetype(font_type, font_size)
    color = "#000000"
    if type(headers) != list:
        draw.text(position, headers, color, font)
        image.save('pic_base.png')
    else:
        draw.multiline_text(position, '\n'.join(headers), color, font)
        image.save('pic_base.png')
#图片合并

def pic_mix(nickname='',bottom_pic='pic_base.png',top_pic='ciyun_run.png',box=(100,100,980,600)):
    #加载底图
    base_img = Image.open(bottom_pic)

    #加载需要P上去的图片
    region = Image.open(top_pic)
    region = region.resize((box[2] - box[0], box[3] - box[1]))
    base_img.paste(region, box)
    base_img.save("./"+ nickname + '/yourneed.png') #保存图片

if __name__ == '__main__':
    
    #输入信息：
    #id = '2113342561' #'1750070171' #用户ID
    #days = 300 #抓取天数
    #抓取数据：
    nickname = main(str(sys.argv[1]),sys.argv[2])
    print("nickname已获取！",nickname)
    path = nickname + os.sep + str(sys.argv[1]) + '.csv'
    
    cloud_content,display_content= get_texts(path,24,5)
    pic_display(pic_blank('mobile'),(100,800),display_content,36)
    pic_display('pic_base.png',(310,650),nickname + '微博词云',65)
    cloud_pic(cloud_content)
    pic_mix(nickname)
    print("请查看生成的图片：need.png")