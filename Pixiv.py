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
download_path = r''

# 可选图片尺寸列表
pic_size_list = ['mini', 'thumb', 'small', 'regular', 'original']

# 榜单数据返回形式
"{'rank': self.rank_num, 'title': self.title_list, 'artist': self.artist_list, 'id': self.pic_id_list}"

# pic_tag_dict构造 {illuist_id:{"jp_tag":'ツムギ(プリコネ)', "cn_tag":'纺希（公主连结）'.......}.......}


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
        self.r18 = False  # 初始化r18设定，可在其余方法中再次关启r18
        self.enable_cache = True  # 是否启用缓存功能
        self.cache_time_gap = 21600  # 缓存刷新间隔(秒)
        self.pic_size_list = ['mini', 'thumb', 'small', 'regular', 'original']

        self.is_that_gif = {}  # 感觉更容易混乱了。

        self.module_path = os.path.dirname(__file__)  # 文件缓存目录
        self.page_1 = ''
        self.page_2 = ''

        self.pixiv = httpx.AsyncClient(http2=True, verify=False, proxies=self.agency)  # http2模式 代理

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

        self.pic_url_dict = {}  # {illuist_id:{'mini':url, 'thumb':url, 'small':url, 'regular':url, 'original':url}}

        self.pic_tag_dict = {}  # 层构造 {illuist_id:{"jp_tag":'ツムギ(プリコネ)', "cn_tag":'纺希（公主连结）'.......}.......}
        self.arranged_rank = []

    async def get_daily_rank(self, r18=False):
        """
        get_daily_rank获取Pixiv榜单信息
        :param r18: bool型 控制榜单类型是否为r18
        :return 详见脚本文件开头
        """
        self.r18 = r18
        self.page_1 = f"{self.module_path}/rank_page_1_{'r18' if self.r18 else 'regular'}.html"  # 缓存榜单文件路径，区分是否为r18
        self.page_2 = f"{self.module_path}/rank_page_2_{'r18' if self.r18 else 'regular'}.json"
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

    async def get_daily_rank_url(self, pic_id_range_start=0, pic_id_range_end=10):
        """
        get_daily_rank_url 获取榜单相应起始范围图片url，并解析tag
        非榜单图片获取url及tag请使用pic_search
        :param illuist_id: 图片id
        :param pic_id_range_start: 图片排行起始位置 0-99
        :param pic_id_range_end: 图片排行结束位置 1-100
        :return url_dict: 图片信息页中不同尺寸url
        返回样式: {illuist_id:{'mini':url, 'thumb':url, 'small':url, 'regular':url, 'original':url}}
        """
        if self.pic_id_list:
            pic_id_list = self.pic_id_list[pic_id_range_start:pic_id_range_end]
        else:
            raise ValueError('get_daily_rank_url 请先获取榜单')

        get_rank_url_task = []
        for pic_id in pic_id_list:
            get_rank_url_task.append(asyncio.create_task(self._get_url(pic_id)))
        url_list = await asyncio.gather(*get_rank_url_task)
        pic_url_dict = dict(zip(pic_id_list, url_list))
        self.pic_url_dict.update(pic_url_dict)
        return pic_url_dict

    async def pic_download(self, download_path: str, pic_url=None, pic_size='regular'):
        """
        pic_download 下载图片
        优先下载参数pic_url图片，如无则尝试从已获取的url下载
        :param download_path: 下载位置全路径
        :param pic_size: 下载图片尺寸
        :param pic_url: 图片url
        :return: pic_file_full_path: 下载完成图片全路径列表
        返回样式: ['C:\\Users\\MSI-PC\\Desktop\\bmss/90112021.jpg',......]
        """
        if pic_url:
            pic_url_list = list(pic_url)
        elif not self.pic_url_dict:
            raise ValueError('get_pic 未输入图片url或榜单图片url未经get_url获取')
        else:
            pic_url_list = [url[pic_size] for url in self.pic_url_dict.values()]
        get_rank_pic_task = []
        for url in pic_url_list:
            get_rank_pic_task.append(asyncio.create_task(self._get_pic(download_path, url)))
        pic_file_full_path = await asyncio.gather(*get_rank_pic_task)
        return pic_file_full_path

    async def pic_search(self, pic_id: str, max_attempt=2) -> dict:
        """
        pic_search Pixiv图片搜索
        :param pic_id: illuist id Pixiv图片id
        :param max_attempt: 最大重试次数
        :return: {'title': title, 'artist': artist, 'url': urls_json_form, 'tag': self.pic_tag_dict[pic_id]}
        """
        print(f'Pixiv搜索, id={pic_id}')
        pic_html = None
        attempt_num = 0
        while attempt_num < max_attempt:
            try:
                pic_html = await self.pixiv.get(f'https://www.pixiv.net/artworks/{pic_id}', headers=self.url_headers, timeout=8)
                break
            except Exception as e:
                print(f'{pic_id} 图片url获取失败', attempt_num)
                attempt_num += 1
        if pic_html.status_code == 404:
            self.state = f'404 {pic_id}图片不存在'
            print(self.state)
            return {}
        else:
            content = pic_html.content.decode('utf-8')
            soup = BeautifulSoup(content, 'html.parser', from_encoding='utf-8')
            preload_content = soup.find_all('meta', id='meta-preload-data')[0]['content']
            urls_json_form = json.loads('{' + re.findall(r'"urls":\{(.*?)\},', preload_content)[0] + '}')
            title = re.findall(r'"illustTitle":"(.*?)",', preload_content)[0]
            artist = re.findall(r'"userName":"(.*?)"\}', preload_content)[0]

            if re.findall('动图', soup.title.string):
                self.is_that_gif.update({pic_id: True})
                print('该图片为gif图，请使用gif_download来下载')
            self._tag_parser(content)
            return {'title': title, 'artist': artist, 'url': urls_json_form, 'tag': self.pic_tag_dict[pic_id]}

    async def gif_download(self, download_path: str, url_unhandled: str):
        """
        gif_download Pixiv动图下载，需要通过pic_search 先获得动图url
        :param download_path: 下载位置全路径
        :param url_unhandled: 未经解析的图片url
        :return gif_file: 动图gif全路径
        """
        print(f'Pixiv动图下载')
        # 构造gif下载url
        gif_host = 'https://i.pximg.net/img-zip-ugoira/img/'
        gif_host_tail = '_ugoira600x600.zip'
        gif_url = gif_host + re.findall(r'/img/(.*)_ugoira0.jpg', url_unhandled)[0] + gif_host_tail
        print(gif_url)
        # 准备临时文件路径
        zip_file_name = re.findall(r'.*/(.*?\.zip)', gif_url)[0]
        zip_file_path = f'{download_path}/{zip_file_name}'
        foder_name = os.path.splitext(zip_file_name)[0]
        foder_path = f'{download_path}/{foder_name}'
        gif_file = f'{download_path}/{foder_name}.gif'
        print(zip_file_name, foder_name, gif_file)
        # 检查是否已存在gif
        if os.path.isfile(gif_file):
            print(f'{gif_file}已存在')
            return gif_file
        # 下载gif
        gif_response = await self.pixiv.get(url=gif_url, headers=self.gif_download_headers, timeout=60)
        print('gif完成下载，处理中')
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

    def _rank_parser(self, response_1_content, response_2_content) -> dict:
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
        return {'rank': self.rank_num, 'title': self.title_list, 'artist': self.artist_list, 'id': self.pic_id_list}

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

    async def _get_url(self, pic_id: str, max_attempt=2):
        await asyncio.sleep(random.randint(0, 10)/10)  # 暂停一下随机时间
        pic_html = None
        attempt_num = 0
        while attempt_num < max_attempt:
            try:
                pic_html = await self.pixiv.get(f'https://www.pixiv.net/artworks/{pic_id}', headers=self.url_headers, timeout=8)
                break
            except Exception as e:
                print(f'{pic_id} 图片url获取失败', attempt_num)
                attempt_num += 1
        if pic_html and pic_html.status_code != 404:
            content = pic_html.content.decode('utf-8')
            soup = BeautifulSoup(content, 'html.parser', from_encoding='utf-8')
            preload_content = soup.find_all('meta', id='meta-preload-data')[0]['content']
            urls_json_form = json.loads('{' + re.findall(r'"urls":\{(.*?)\},', preload_content)[0] + '}')
            print(f'获取url，id={pic_id}')
            self._tag_parser(content)
            return urls_json_form
        elif pic_html.status_code == 404:
            self.state = f'404 {pic_id}图片不存在'
            print(self.state)
            return False
        else:
            return False

    async def _get_pic(self, download_path: str, pic_url: str, max_attempt=2):
        pic_file_name = self._image_url2name(pic_url)
        if os.path.isfile(f'{download_path}/{pic_file_name}') and (os.path.getsize(f'{download_path}/{pic_file_name}') >= 1000):
            print(f'图片ID{pic_file_name}已存在')
            return f'{download_path}/{pic_file_name}'

        await asyncio.sleep(random.randint(0, 10) / 10)  # 暂停一下随机时间
        pic = None
        attempt_num = 0
        while attempt_num < max_attempt:
            try:
                pic = await self.pixiv.get(pic_url, headers=self.download_headers, timeout=10)
                break
            except Exception as e:
                print(f'{pic_file_name} 图片下载失败', attempt_num)
                attempt_num += 1

        with open(f'{download_path}/{pic_file_name}', 'wb') as f:
            f.write(pic.content)
        print(f'图片ID{pic_file_name}下载完成')
        return f'{download_path}/{pic_file_name}'

    def _tag_parser(self, content):  # 不能外部调用。只能通过get_url 方法，并开启tag解析，访问pic_tag_dict
        soup = BeautifulSoup(content, 'html.parser', from_encoding='utf-8')
        preload_content = soup.find_all('meta', id='meta-preload-data')[0]['content']
        illust_id = re.findall(r'"illust":\{"(.*?)"', preload_content)[0]
        print(f'处理tag，id={illust_id}')
        tags_json_form = json.loads('{' + re.findall(r'"tags":\[.*?\]', preload_content)[0] + '}')
        tag_dict = {}
        for tag in tags_json_form['tags']:
            jp_tag = tag['tag']
            cn_tag = tag['translation']['en'] if "translation" in tag else ''
            tag_dict.update({jp_tag: cn_tag})
        self.pic_tag_dict.update({illust_id: tag_dict})
        return self.pic_tag_dict


async def rank_test():
    """
    Pixiv榜单数据获取及图片下载示例
    """
    # 实例化Pixiv
    p = Pixiv()

    # 获取p站榜单
    # r18关键词控制榜单类型
    rank_dict = await p.get_daily_rank(r18=False)
    print(rank_dict)

    # 获取p站榜单图片url
    # 通过pic_id_range_start, pic_id_range_end 限定范围（一次调用中建议范围小于20，防止被查）
    # 这一步将包含tag标签解析
    url_dict = await p.get_daily_rank_url(pic_id_range_start=10, pic_id_range_end=20)
    print(url_dict)

    # 榜单图片tag标签获取方式
    # 必须在get_daily_rank_url、pic_search方法之后
    print('tag示例:', p.pic_tag_dict[rank_dict['id'][10]])

    # 榜单图片下载
    # 未输入pic_url列表或字符串，则默认下载经get_daily_rank_url方法获得url的图片。
    # 可设置pic_size 下载图片规格
    download_report = await p.pic_download(pic_url=None, download_path=download_path, pic_size='regular')
    print(download_report)

    # 手动关闭httpx异步客户端，不介意报错也可以不管= =
    await p.pixiv.aclose()


async def search_test():
    """
    Pixiv单图搜索，及gif下载示例
    """
    # 实例化Pixiv
    p = Pixiv()
    illuist_id = '91047813'

    # 搜索独立图片时，使用pic_search
    search_report = await p.pic_search(illuist_id)
    print(search_report)

    # 判断该图是否为gif图
    if p.is_that_gif[illuist_id]:
        # gif_download方法url_unhandled参数传入任意尺寸图片url皆可
        download_report = await p.gif_download(download_path=download_path, url_unhandled=search_report['url']['original'])
        print(download_report)
    else:
        download_report = await p.pic_download(download_path=download_path, pic_url=search_report['url']['original'])
        print(download_report)

    # 手动关闭httpx异步客户端，不介意报错也可以不管= =
    await p.pixiv.aclose()


if __name__ == '__main__':
    asyncio.run(rank_test())
    await asyncio.sleep(5)
    asyncio.run(search_test())

