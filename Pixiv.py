import asyncio
import os
import time
import re
import json
import random
import httpx
from bs4 import BeautifulSoup
import zipfile
import imageio


# 代理地址
agency = r'http://localhost:4780'

# 榜单请求cookie 及 图片页请求cookie
rank_headers_cookie = r''
pic_info_headers_cookie = r''

# 图片下载位置全路径（作为脚本运行时）
download_path_global = r''

# 可选图片尺寸列表
pic_size_list = ['mini', 'thumb', 'small', 'regular', 'original']


class Pixiv:
    """
    Pixiv榜单爬虫
    python 3.7.2 及以上
    依赖：httpx（网络请求）
         bs4（页面解析）
         zipfile、imageio（动图文件处理）
    """

    def __init__(self):
        self.state = 200
        self.agency = agency  # 代理地址
        self.enable_cache = True  # 是否启用缓存功能
        self.cache_time_gap = 21600  # 缓存刷新间隔(秒)
        self.pic_size_list = ['mini', 'thumb', 'small', 'regular', 'original']

        self.r18 = False
        self.module_path = os.path.dirname(__file__)  # 文件缓存目录
        self.page_1 = ''
        self.page_2 = ''

        self.pixiv = httpx.AsyncClient(http2=True, verify=False, proxies=self.agency)  # 异步客户端 http2模式 代理

        self.rank_headers = {
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cookie': rank_headers_cookie,
            'referer': 'https://www.pixiv.net/ranking.php',
        }
        self.url_headers = {
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cookie': pic_info_headers_cookie,
        }
        self.download_headers = {
            'accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'referer': 'https://www.pixiv.net/artworks/Host',
            'sec-fetch-dest': 'image',
        }
        self.gif_download_headers = {
            'accept-encoding': 'identity',
            'origin': 'https://www.pixiv.net',
            'referer': 'https://www.pixiv.net/',
            'sec-ch-ua': '"Google Chrome";v="87", " Not;A Brand";v="99", "Chromium";v="87"',
        }
        self.params_r18_page_1 = {'mode': 'daily_r18'}
        self.params_r18_page_2 = {'mode': 'daily_r18', 'p': '2', 'format': 'json'}
        self.params_regular_page_1 = {'mode': 'daily'}
        self.params_regular_page_2 = {'mode': 'daily', 'p': '2', 'format': 'json'}

        self.rank_num = []
        self.title_list = []
        self.artist_list = []
        self.pic_id_list = []

    async def daily_rank(self, r18=False):
        """
        daily_rank Pixiv每日榜单
        :param r18: r18榜单
        :return rank_id_list: 每日榜单前100 图片illuist id 列表（按排名顺序）
        """
        self.r18 = r18
        self.page_1 = f"{self.module_path}/rank_page_1_{'r18' if r18 else 'regular'}.html"  # 缓存榜单文件路径，区分是否为r18
        self.page_2 = f"{self.module_path}/rank_page_2_{'r18' if r18 else 'regular'}.json"
        if self.enable_cache and self._rank_cache_check():  # 检查是否启用缓存功能及榜单缓存文件
            content_1, content_2 = self._rank_cache_read()
            return self._rank_parser(content_1, content_2)
        params_1 = self.params_r18_page_1 if r18 else self.params_regular_page_1
        params_2 = self.params_r18_page_2 if r18 else self.params_regular_page_2
        try:
            response_1 = await self.pixiv.get('https://www.pixiv.net/ranking.php', params=params_1, headers=self.rank_headers, timeout=10)
            response_2 = await self.pixiv.get('https://www.pixiv.net/ranking.php', params=params_2, headers=self.rank_headers, timeout=8)
            print(f"Pxiv榜单状态码:{response_1.status_code} {response_2.status_code}")
        except Exception as e:
            print(f'榜单数据获取失败，请重试{e}')
            self.state = f'榜单数据获取失败，请重试 {e}'
            return False
        content_1 = response_1.content.decode('utf-8')
        content_2 = response_2.content.decode('utf-8')
        if self.enable_cache:
            self._rank_cache_write(content_1, content_2)
        return self._rank_parser(content_1, content_2)

    async def illustration_detail_parser(self, pic_id_list: list):
        """
        illustration_detail_parser Pixiv插图详情
        :param pic_id_list: 需要解析的illuist id 列表
        :return: 图片详情 {pic_id: {'title': '', 'artist': '', 'tag': {}, 'url': {'mini': '', 'thumb': '', 'small': '',
         'regular': '', 'original': ''}, 'r18': False, 'gif': False}}
        """
        illustration_detail_dict = {}
        task = [asyncio.create_task(self._illustration_detail_parser(pic_id)) for pic_id in pic_id_list]
        illustration_detail_list = await asyncio.gather(*task)
        for i in illustration_detail_list:
            illustration_detail_dict.update(i)
        return illustration_detail_dict

    async def illustration_downloader(self, download_path: str, illustration_detail: dict, pic_size='regular'):
        """
        illustration_downloader Pixiv插图下载
        :param download_path: 下载位置全路径
        :param illustration_detail: illustration_detail_parser获取的插图详情
        :param pic_size: 需下载图片尺寸
        :return: 下载完成图片全路径
        """
        task = []
        for key in illustration_detail.keys():
            url = illustration_detail[key]['url'][pic_size]
            if illustration_detail[key]['gif'] is False:
                task.append(asyncio.create_task(self._pic_downloader(download_path, url)))
            elif illustration_detail[key]['gif'] is True:
                task.append(asyncio.create_task(self.gif_downloader(download_path, url)))
        pic_file_full_path = await asyncio.gather(*task)
        return pic_file_full_path

    def _rank_cache_check(self) -> bool:
        print(f"Pixiv 获取{'r18' if self.r18 else '常规'}榜单 {f'启用{self.cache_time_gap}秒' if self.enable_cache else '未启用'}缓存")
        if os.path.isfile(self.page_1) and os.path.isfile(self.page_2):
            if os.stat(self.page_1).st_mtime + self.cache_time_gap < time.time():
                return False
            else:
                return True
        else:
            return False

    def _rank_cache_read(self):
        print(f"读取Pxivi {'r18' if self.r18 else '常规'}榜单缓存")
        with open(self.page_1, 'rb') as res_1:
            response_1_content = res_1.read()
        with open(self.page_2, 'rb') as res_2:
            response_2_content = res_2.read()
        return response_1_content, response_2_content

    def _rank_cache_write(self, response_1_content, response_2_content):
        print(f"写入Pxivi {'r18' if self.r18 else '常规'}榜单缓存")
        with open(self.page_1, 'w', encoding='utf-8') as res_1:
            res_1.write(response_1_content)
        with open(self.page_2, 'w', encoding='utf-8') as res_2:
            res_2.write(response_2_content)

    @staticmethod
    def _image_url2name(pic_url: str) -> str:
        file_name = pic_url.split('/')[-1]  # 仅限pixiv，图片url很规整
        file_name = file_name.split('_')[0] + '.' + file_name.split('.')[-1]  # 仔细想了下，还是改回简单的id号文件名
        return file_name

    def _rank_parser(self, response_1_content, response_2_content):
        rank_html_1 = BeautifulSoup(response_1_content, 'html.parser', from_encoding='utf-8')
        rank_items_1 = rank_html_1.find_all(class_='ranking-item')
        for rank_item in rank_items_1:
            self.rank_num.append(rank_item['data-rank-text'].replace('#', ''))
            self.title_list.append(rank_item['data-title'])
            self.artist_list.append(rank_item['data-user-name'])
            self.pic_id_list.append(rank_item['data-id'])
        rank_html_2 = json.loads(response_2_content)
        rank_items_2 = rank_html_2['contents']
        for rank_item in rank_items_2:
            self.rank_num.append(str(rank_item['rank']))
            self.title_list.append(rank_item['title'])
            self.artist_list.append(rank_item['user_name'])
            self.pic_id_list.append(rank_item['illust_id'])
        return self.pic_id_list

    async def _illustration_detail_parser(self, pic_id: str, max_attempt=2):
        print(f'图片解析{pic_id}')
        pic_html = None
        attempt_num = 0
        while attempt_num < max_attempt:
            try:
                pic_html = await self.pixiv.get(f'https://www.pixiv.net/artworks/{pic_id}', headers=self.url_headers, timeout=8)
                break
            except Exception as e:
                print(f'图片解析{pic_id} 失败', attempt_num)
                attempt_num += 1

        if (pic_html is None) or (pic_html.status_code == 404):
            return {pic_id: {'title': '', 'artist': '', 'tag': {}, 'url': {'mini': '', 'thumb': '', 'small': '', 'regular': '', 'original': ''}, 'r18': False, 'gif': False}}
        elif pic_html.status_code != 404:
            content = pic_html.content.decode('utf-8')
            soup = BeautifulSoup(content, 'html.parser', from_encoding='utf-8')
            preload_content = soup.find_all('meta', id='meta-preload-data')[0]['content']

            title = re.findall(r'"illustTitle":"(.*?)",', preload_content)[0]  # 标题
            artist = re.findall(r'"userName":"(.*?)"\}', preload_content)[0]  # 作者
            urls_json_form = json.loads('{' + re.findall(r'"urls":\{(.*?)\},', preload_content)[0] + '}')  # url字典
            tags_json_form = json.loads('{' + re.findall(r'"tags":\[.*?\]', preload_content)[0] + '}')  # tag标签字典
            tag_dict = {}
            for tag in tags_json_form['tags']:
                jp_tag = tag['tag']
                cn_tag = tag['translation']['en'] if "translation" in tag else ''
                tag_dict.update({jp_tag: cn_tag})
            gif = bool(re.findall('动图', soup.title.string))  # 是否为gif图
            r18 = bool('R-18' in tag_dict.keys())  # 是否为r18图
            return {pic_id: {'title': title, 'artist': artist, 'tag': tag_dict, 'url': urls_json_form, 'r18': r18, 'gif': gif}}

    async def _pic_downloader(self, download_path: str, pic_url: str, max_attempt=2) -> str:
        if not pic_url:
            return ''
        pic_file_name = self._image_url2name(pic_url)
        if os.path.isfile(f'{download_path}/{pic_file_name}') and (os.path.getsize(f'{download_path}/{pic_file_name}') >= 1000):
            print(f'图片{pic_file_name}已存在')
            return f'{download_path}/{pic_file_name}'

        pic = None
        attempt_num = 0
        while attempt_num < max_attempt:
            try:
                pic = await self.pixiv.get(pic_url, headers=self.download_headers, timeout=15)
                break
            except Exception as e:
                print(f'图片下载{pic_file_name} 失败', attempt_num)
                attempt_num += 1
        if pic is None:
            return ''
        else:
            with open(f'{download_path}/{pic_file_name}', 'wb') as f:
                f.write(pic.content)
            print(f'图片下载{pic_file_name}完成')
            return f'{download_path}/{pic_file_name}'

    async def gif_downloader(self, download_path: str, url_unhandled: str):
        gif_address = re.findall(r'/img/(.*)_', url_unhandled)[0]
        print(f"动图下载{gif_address}")
        # 构造gif下载url
        gif_host = 'https://i.pximg.net/img-zip-ugoira/img/'
        gif_host_tail = '_ugoira600x600.zip'
        gif_url = gif_host + re.findall(r'/img/(.*)_', url_unhandled)[0] + gif_host_tail
        # 准备临时文件路径
        zip_file_name = re.findall(r'.*/(.*?\.zip)', gif_url)[0]
        zip_file_path = f'{download_path}/{zip_file_name}'
        foder_name = os.path.splitext(zip_file_name)[0]
        foder_path = f'{download_path}/{foder_name}'
        gif_file = f'{download_path}/{foder_name}.gif'
        # 检查是否已存在gif
        if os.path.isfile(gif_file):
            print(f'{gif_file}已存在')
            return gif_file
        # 下载gif
        try:
            gif_response = await self.pixiv.get(url=gif_url, headers=self.gif_download_headers, timeout=30)
        except Exception as e:
            print(f"动图下载{gif_address}失败")
            return ''
        print('下载完成，处理中')
        with open(zip_file_path, 'wb') as f:
            f.write(gif_response.content)
        # 解压gif文件
        zip_file = zipfile.ZipFile(zip_file_path)
        os.mkdir(foder_path)
        zip_file.extractall(foder_path)
        zip_file.close()
        os.remove(zip_file_path)
        # 合成gif图片，并删除临时文件
        pictures = os.listdir(foder_path)
        gif_frame = []
        for picture in pictures:
            gif_frame.append(imageio.imread(f'{foder_path}/' + picture))
            os.remove(f'{foder_path}/' + picture)
        os.rmdir(foder_path)
        imageio.mimsave(gif_file, gif_frame, duration=0.086)
        return gif_file


async def rank_test():
    """
    Pixiv榜单数据获取及图片下载示例
    """
    # 实例化Pixiv
    p = Pixiv()

    # 获取p站榜单
    # r18关键词控制榜单类型
    id_list = await p.daily_rank(r18=False)
    print(id_list)

    # 获取p站榜单图片详情
    # 通过列表切片 限定范围（一次调用中建议范围小于20，防止被查）
    # {pic_id: {'title': '', 'artist': '', 'tag': {}, 'url': {'mini': '', 'thumb': '', 'small': '', 'regular': '',
    # 'original': ''}, 'r18': False, 'gif': False}} 返回格式
    illuist_detail_dict = await p.illustration_detail_parser(id_list[20:30])
    print(illuist_detail_dict)

    # 榜单图片tag标签获取方式
    # 必须在get_daily_rank_url、pic_search方法之后
    # print('tag示例:', p.pic_tag_dict[rank_dict['id'][10]])

    # 榜单图片下载
    # illustration_detail直接传入上一步的返回
    # 可设置pic_size 图片规格尺寸
    download_report = await p.illustration_downloader(download_path=download_path_global, illustration_detail=illuist_detail_dict, pic_size='regular')
    print(download_report)

    # 手动关闭httpx异步客户端，不介意报错也可以不管= =
    await p.pixiv.aclose()


async def search_test():
    """
    Pixiv单图搜索，及gif下载示例
    """
    # 实例化Pixiv
    p = Pixiv()

    # 字符串列表 形式图片id
    illuist_id = ['91855805']

    # 获取p站榜单图片详情
    # 通过列表切片 限定范围（一次调用中建议范围小于20，防止被查）
    # {pic_id: {'title': '', 'artist': '', 'tag': {}, 'url': {'mini': '', 'thumb': '', 'small': '', 'regular': '',
    # 'original': ''}, 'r18': False, 'gif': False}} 返回格式
    search_report = await p.illustration_detail_parser(illuist_id)
    print(search_report)

    # 榜单图片下载
    # illustration_detail直接传入上一步的返回
    # 可设置pic_size 图片规格尺寸
    download_report = await p.illustration_downloader(download_path=download_path_global, illustration_detail=search_report)
    print(download_report)

    # 手动关闭httpx异步客户端，不介意报错也可以不管= =
    await p.pixiv.aclose()


if __name__ == '__main__':
    asyncio.run(rank_test())
    asyncio.run(search_test())

