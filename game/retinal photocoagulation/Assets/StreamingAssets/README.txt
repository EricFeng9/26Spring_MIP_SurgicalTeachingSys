将眼底图像放到 StreamingAssets 目录后，手术场景会自动尝试加载。
可用路径优先级：
1) Assets/StreamingAssets/fundus.jpg
2) Assets/StreamingAssets/fundus.png
3) Assets/StreamingAssets/Retina/fundus.jpg
4) Assets/StreamingAssets/Retina/fundus.png

如果都不存在，会自动使用内置占位眼底图。
