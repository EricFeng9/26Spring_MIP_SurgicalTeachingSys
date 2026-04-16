using System.IO;
using UnityEditor;
using UnityEngine;

public static class GenerateSlitLampGradients
{
    private const int Width = 256;
    private const int Height = 64;
    private const string OutputFolder = "Assets/SimulationResources/Sprites/Generated";

    [MenuItem("Tools/Generate/Slit Lamp Gradient Sprites")]
    public static void Generate()
    {
        if (!Directory.Exists(OutputFolder))
            Directory.CreateDirectory(OutputFolder);

        GenerateGradient("GradientBlack_Left.png", leftToRightTransparent: true);
        GenerateGradient("GradientBlack_Right.png", leftToRightTransparent: false);

        AssetDatabase.Refresh();

        SetAsSprite(Path.Combine(OutputFolder, "GradientBlack_Left.png"));
        SetAsSprite(Path.Combine(OutputFolder, "GradientBlack_Right.png"));

        AssetDatabase.Refresh();
        Debug.Log("已生成裂隙灯渐变图：Left / Right");
    }

    private static void GenerateGradient(string fileName, bool leftToRightTransparent)
    {
        Texture2D tex = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
        tex.wrapMode = TextureWrapMode.Clamp;
        tex.filterMode = FilterMode.Bilinear;

        for (int y = 0; y < Height; y++)
        {
            for (int x = 0; x < Width; x++)
            {
                // float t = x / (float)(Width - 1);

                // // true: 左边黑，往右逐渐透明
                // // false: 左边透明，往右逐渐变黑
                // float a = leftToRightTransparent ? (1f - t) : t;
                // float alpha = Mathf.Pow(a, 0.35f);
                float t = x / (float)(Width - 1);

                // blackPortion = 0.9 表示 90% 都是纯黑
                float blackPortion = 0.8f;
                float fadeT;

                if (leftToRightTransparent)
                {
                    if (t <= blackPortion)
                        fadeT = 1f;
                    else
                        fadeT = 1f - ((t - blackPortion) / (1f - blackPortion));
                }
                else
                {
                    if (t >= 1f - blackPortion)
                        fadeT = 1f;
                    else
                        fadeT = t / (1f - blackPortion);
                }

                float alpha = Mathf.Clamp01(fadeT);
                Color c = new Color(0f, 0f, 0f, alpha);
                tex.SetPixel(x, y, c);
            }
        }

        tex.Apply();

        byte[] png = tex.EncodeToPNG();
        File.WriteAllBytes(Path.Combine(OutputFolder, fileName), png);

        Object.DestroyImmediate(tex);
    }

    private static void SetAsSprite(string assetPath)
    {
        AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);

        TextureImporter importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer == null) return;

        importer.textureType = TextureImporterType.Sprite;
        importer.spriteImportMode = SpriteImportMode.Single;
        importer.alphaIsTransparency = true;
        importer.mipmapEnabled = false;
        importer.wrapMode = TextureWrapMode.Clamp;
        importer.filterMode = FilterMode.Bilinear;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.SaveAndReimport();
    }
}