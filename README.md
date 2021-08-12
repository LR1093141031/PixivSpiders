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
download_path_global = ''  # 图片下载位置全路径（作为脚本运行时）
```



![p站cookie获取](C:\Users\MSI-PC\Desktop\GitHub\PixivSpiders\p站cookie获取.jpg)

### 使用

使用示例在Pixiv.py 脚本文件末尾

```python
daily_rank返回示例
['91882132', '91857578', '91856307', '91856552', '91865886']

illustration_detail_parser返回示例
{'91875603': {'title': 'THE STAR', 'artist': 'Coul', 'tag': {'fgo': '', 'Fate/GrandOrder': '', 'Fate': '', 'アルトリア・キャスター': '阿尔托莉雅·Caster', 'オベロン(Fate)': 'Oberon (Fate)', 'オベロン・ヴォーティガーン': '', 'タロットカード': 'tarot card', 'Fate/GO1000users入り': 'Fate/GO1000users加入书籤'}, 'url': {'mini': 'https://i.pximg.net/c/48x48/img-master/img/2021/08/10/20/56/01/91875603_p0_square1200.jpg', 'thumb': 'https://i.pximg.net/c/250x250_80_a2/img-master/img/2021/08/10/20/56/01/91875603_p0_square1200.jpg', 'small': 'https://i.pximg.net/c/540x540_70/img-master/img/2021/08/10/20/56/01/91875603_p0_master1200.jpg', 'regular': 'https://i.pximg.net/img-master/img/2021/08/10/20/56/01/91875603_p0_master1200.jpg', 'original': 'https://i.pximg.net/img-original/img/2021/08/10/20/56/01/91875603_p0.jpg'}, 'r18': False, 'gif': False}

illustration_downloader返回示例
['C:\\Users\\MSI-PC\\Desktop\\bmss/91875603.jpg]

```



```python
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
```

```python
    """
    Pixiv单图搜索，及gif下载示例
    """
    # 实例化Pixiv
    p = Pixiv()

    # 字符串列表 形式图片id
    illuist_id = ['91855805']

    # 获取p站榜单图片详情
    # 通过列表切片 限定范围（一次调用中建议范围小于20，防止被查）
    # {pic_id: {'title': '', 'artist': '', 'tag': {}, 'url': {'mini': '', 'thumb': '', 'small': '', 'regular': '', 'original': ''}, 'r18': False, 'gif': False}} 返回格式
    search_report = await p.illustration_detail_parser(illuist_id)
    print(search_report)

    # 榜单图片下载
    # illustration_detail直接传入上一步的返回
    # 可设置pic_size 图片规格尺寸
    download_report = await p.illustration_downloader(download_path=download_path_global,illustration_detail=search_report)
    print(download_report)

    # 手动关闭httpx异步客户端，不介意报错也可以不管= =
    await p.pixiv.aclose()

```

总之能用！

——2021.8.12