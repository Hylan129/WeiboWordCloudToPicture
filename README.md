# WeiboWordCloudToPicture
这是一个小工具。

用于提取微博原创微博文本内容，分析并创建词云图；同时获取近期热门原创点赞微博top3；将以上信息结合在一起生成图片展示，便于发微博或者发朋友圈。

## 使用说明

1、主程序：weibocloud.py 

2、调用方法：python weibocloud.py  weibo_id         needAnalysis_Days 

>#### 以人民日报微博为示例，分析数据时间30天内：
> python weibocloud.py 2803301701         30
   
3、运行结果保存在对应微博文件夹下，文件名称：yourneed.png

4、生成图片结果展示如下：

 ![人民日报微博词云](https://github.com/Hylan129/WeiboWordCloudToPicture/blob/master/人民日报/yourneed.png)
