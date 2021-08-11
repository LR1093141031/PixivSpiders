# Pixiv爬虫

### 简单粗暴的P站榜单爬虫，现实现以下功能

- [x] 每日榜单
- [x] 图片搜索
- [x] gif图下载
- [ ] 画师搜索

### 依赖与准备

环境：python3.7.2及以上

依赖包：httpx、bs4、zipfile、imageio

未实现Pixiv模拟登陆，需要自行登陆Pixiv并复制登陆cookie到脚本中。

需求cookie：1.P站每日榜单页面cookie

​					 2.P站图片详情页面cookie

获取cookie方法：登陆Pixiv访问榜单及图片详情页、F12进入开发者模式、找到ranking.php-Headers-RequestHeaders-cookie，复制该cookie字符串到脚本中。

脚本文件中需要自行填入的部分：

Pixiv.py

```python
agency = ''  # 代理地址，国内访问一般需要
rank_headers_cookie = ''  # Pixiv榜单cookie
pic_info_headers_cookie = ''  # Pixiv图片详情页cookie
download_path = ''  # 图片下载位置全路径（作为脚本运行时）
```



![p站cookie获取](C:\Users\MSI-PC\Desktop\GitHub\PixivSpiders\p站cookie获取.jpg)

### 使用

使用示例在Pixiv.py 脚本文件末尾

```python
"""
Pixiv榜单数据获取及图片下载示例
"""
# 获取榜单及图片时流程：1.实例化 2.获取榜单内容 3.获取榜单图片url 4.下载图片
# 获取榜单将返回{'rank': self.rank_num, 'title': self.title_list, 'artist': self.artist_list, 'id': self.pic_id_list}排行榜图片排名、标题、作者、图片id
# 由于图片tag无法在榜单中获取，图片包含的tag将在获取图片详情页的get_daily_rank_url、pic_search中解析，访问请通过类属性pic_tag_dict[illuist_id]来获得

# 实例化Pixiv
p = Pixiv()

# 获取p站榜单
# r18关键词控制榜单类型
rank_dict = await p.get_daily_rank(r18=False)

# 获取p站榜单图片url
# 通过pic_id_range_start, pic_id_range_end 限定范围（一次调用中建议范围小于20，防止被查）
# 这一步将包含tag标签解析，pic_tag_dict构造 {illuist_id:{"jp_tag":'ツムギ(プリコネ)', "cn_tag":'纺希（公主连结）'.......}.......}

url_dict = await p.get_daily_rank_url(pic_id_range_start=10, pic_id_range_end=20)

# 榜单图片tag标签获取方式，10为图片榜单排名
# 必须在get_daily_rank_url、pic_search方法之后
print('tag示例:', p.pic_tag_dict[rank_dict['id'][10]])

# 榜单图片下载
# 未输入pic_url列表或字符串，则默认下载经get_daily_rank_url方法获得url的图片。
# 可设置pic_size 下载图片规格
download_report = await p.pic_download(pic_url=None, download_path=r'C:\Users\MSI-PC\Desktop\bmss', pic_size='regular')

# 手动关闭httpx异步客户端，不介意报错也可以不管= =
await p.pixiv.aclose()
```

```python
"""
Pixiv单图搜索，及gif下载示例
"""
# 图片搜索流程 1.实例化 2.搜索图片(不存在则返回空字典) 3.通过is_that_gif属性判断该图片是否为gif图片(不通过gif_download下载则仅会下载gif第一帧) 4.下载图片
# 实例化Pixiv
p = Pixiv()
illuist_id = '91047813'

# 搜索独立图片时，使用pic_search
search_report = await p.pic_search(illuist_id)

# 判断该图是否为gif图
if p.is_that_gif[illuist_id]:
    # gif_download方法url_unhandled参数传入任意尺寸图片url皆可
    download_report = await p.gif_download(download_path=r'C:\Users\MSI-PC\Desktop\bmss', url_unhandled=search_report['url']['original'])
else:
    download_report = await p.pic_download(download_path=r'C:\Users\MSI-PC\Desktop\bmss', pic_url=search_report['url']['original'])

# 手动关闭httpx异步客户端，不介意报错也可以不管= =
await p.pixiv.aclose()
```

啊~~总之有点混乱，但是能用！

——2021.8.11