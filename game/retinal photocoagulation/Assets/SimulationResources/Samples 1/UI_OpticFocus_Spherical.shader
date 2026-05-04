Shader "UI/OpticFocus_Spherical"
{
    Properties
    {
        [PerRendererData] _MainTex ("Sprite Texture", 2D) = "white" {}
        _Color ("Tint", Color) = (1,1,1,1)
        
        // 核心：当前焦平面的深度 (0 = 对焦在正中心，1 = 对焦在最边缘)
        _FocusDepth ("Focal Plane Depth", Range(0, 1)) = 0 
        
        // 眼底弯曲度：数值越大，边缘和中心的落差越大（可以在材质球里微调）
        _Curvature ("Retina Curvature", Range(0, 5)) = 2.0
        
        // 最大失焦程度：也就是最大使用第几级的 Mipmap
        _MaxBlur ("Max Blur Level", Range(0, 10)) = 7.0

        // 兼容 UGUI 遮罩系统的必须参数
        _StencilComp ("Stencil Comparison", Float) = 8
        _Stencil ("Stencil ID", Float) = 0
        _StencilOp ("Stencil Operation", Float) = 0
        _StencilWriteMask ("Stencil Write Mask", Float) = 255
        _StencilReadMask ("Stencil Read Mask", Float) = 255
        _ColorMask ("Color Mask", Float) = 15
    }

    SubShader
    {
        Tags
        {
            "Queue"="Transparent"
            "IgnoreProjector"="True"
            "RenderType"="Transparent"
            "PreviewType"="Plane"
            "CanUseSpriteAtlas"="True"
        }

        Stencil
        {
            Ref [_Stencil]
            Comp [_StencilComp]
            Pass [_StencilOp]
            ReadMask [_StencilReadMask]
            WriteMask [_StencilWriteMask]
        }

        Cull Off
        Lighting Off
        ZWrite Off
        ZTest [unity_GUIZTestMode]
        Blend SrcAlpha OneMinusSrcAlpha
        ColorMask [_ColorMask]

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            #include "UnityUI.cginc"

            struct appdata_t { float4 vertex : POSITION; float4 color : COLOR; float2 texcoord : TEXCOORD0; };
            struct v2f { float4 vertex : SV_POSITION; fixed4 color : COLOR; float2 texcoord : TEXCOORD0; };

            sampler2D _MainTex;
            fixed4 _Color;
            float _FocusDepth;
            float _Curvature;
            float _MaxBlur;

            v2f vert(appdata_t v)
            {
                v2f OUT;
                OUT.vertex = UnityObjectToClipPos(v.vertex);
                OUT.texcoord = v.texcoord;
                OUT.color = v.color * _Color;
                return OUT;
            }

            fixed4 frag(v2f IN) : SV_Target
            {
                // 1. 算距离：当前像素离图片中心 (0.5, 0.5) 有多远
                float2 center = float2(0.5, 0.5);
                float distFromCenter = distance(IN.texcoord, center);

                // 2. 算深度：由于视网膜是球面的，越靠近边缘深度越大（利用抛物线模拟球面）
                float surfaceDepth = pow(distFromCenter * 2.0, 2.0) * _Curvature;

                // 3. 算偏焦：物理表面深度 - 镜头焦平面深度 = 失焦量
                float outOfFocusAmount = abs(surfaceDepth - _FocusDepth);

                // 4. 算模糊：把失焦量映射到 Mipmap 的层级上
                float mipLevel = clamp(outOfFocusAmount * _MaxBlur, 0.0, _MaxBlur);

                // 5. 光学成像：直接读取对应模糊层级的纹理像素
                half4 color = tex2Dlod(_MainTex, float4(IN.texcoord.x, IN.texcoord.y, 0, mipLevel));
                
                return color * IN.color;
            }
            ENDCG
        }
    }
}