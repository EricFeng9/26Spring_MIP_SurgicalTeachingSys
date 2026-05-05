using System.Collections.Generic;
using UnityEngine;

namespace RetinalPrototype.Hub
{
    public static class SpriteTransparentCropper
    {
        private struct CacheKey
        {
            public int spriteId;
            public int thresholdBucket;
        }

        private static readonly Dictionary<CacheKey, Sprite> Cache = new Dictionary<CacheKey, Sprite>();

        public static Sprite GetCroppedSprite(Sprite source, float alphaThreshold)
        {
            if (source == null || source.texture == null)
            {
                return source;
            }

            var key = new CacheKey
            {
                spriteId = source.GetInstanceID(),
                thresholdBucket = Mathf.RoundToInt(Mathf.Clamp01(alphaThreshold) * 255f)
            };

            if (Cache.TryGetValue(key, out var cached) && cached != null)
            {
                return cached;
            }

            if (!source.texture.isReadable)
            {
                Debug.LogWarning($"Sprite '{source.name}' texture is not readable. Enable Read/Write if transparent-border cropping is needed.");
                return source;
            }

            Rect sourceRect = source.textureRect;
            int startX = Mathf.FloorToInt(sourceRect.x);
            int startY = Mathf.FloorToInt(sourceRect.y);
            int width = Mathf.FloorToInt(sourceRect.width);
            int height = Mathf.FloorToInt(sourceRect.height);

            int minX = width;
            int minY = height;
            int maxX = -1;
            int maxY = -1;
            float threshold = Mathf.Clamp01(alphaThreshold);

            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    Color pixel = source.texture.GetPixel(startX + x, startY + y);
                    if (pixel.a <= threshold)
                    {
                        continue;
                    }

                    minX = Mathf.Min(minX, x);
                    minY = Mathf.Min(minY, y);
                    maxX = Mathf.Max(maxX, x);
                    maxY = Mathf.Max(maxY, y);
                }
            }

            if (maxX < minX || maxY < minY)
            {
                return source;
            }

            var croppedRect = new Rect(
                startX + minX,
                startY + minY,
                maxX - minX + 1,
                maxY - minY + 1
            );

            Vector2 pivot = new Vector2(0.5f, 0.5f);
            Sprite cropped = Sprite.Create(
                source.texture,
                croppedRect,
                pivot,
                source.pixelsPerUnit,
                0,
                SpriteMeshType.FullRect,
                Vector4.zero
            );

            cropped.name = source.name + "_CroppedVisible";
            Cache[key] = cropped;
            return cropped;
        }
    }
}
