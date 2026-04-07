Shader "Custom/UIBlur_WithMask" {
    Properties {
        [PerRendererData] _MainTex ("Sprite Texture", 2D) = "white" {}
        _BlurSize ("Blur Size", Float) = 0
        
        // --- 必须增加以下属性来支持 Mask ---
        _StencilComp ("Stencil Comparison", Float) = 8
        _Stencil ("Stencil ID", Float) = 0
        _StencilOp ("Stencil Operation", Float) = 0
        _StencilWriteMask ("Stencil Write Mask", Float) = 255
        _StencilReadMask ("Stencil Read Mask", Float) = 255
        _ColorMask ("Color Mask", Float) = 15
        [Toggle(UNITY_UI_ALPHACLIP)] _UseUIAlphaClip ("Use Alpha Clip", Float) = 0
    }

    SubShader {
        Tags { 
            "Queue"="Transparent" 
            "IgnoreProjector"="True" 
            "RenderType"="Transparent" 
            "PreviewType"="Plane"
            "CanUseSpriteAtlas"="True"
        }
        
        // --- 必须增加 Stencil 块 ---
        Stencil {
            Ref [_Stencil]
            Comp [_StencilComp]
            Pass [_StencilOp] 
            ReadMask [_StencilReadMask]
            WriteMask [_StencilWriteMask]
        }
        ColorMask [_ColorMask]

        Cull Off
        Lighting Off
        ZWrite Off
        ZTest [unity_GUIZTestMode]
        Blend SrcAlpha OneMinusSrcAlpha

        Pass {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            #include "UnityUI.cginc" // 必须包含这个库来处理裁切

            struct appdata {
                float4 vertex : POSITION;
                float4 color  : COLOR;
                float2 uv : TEXCOORD0;
            };

            struct v2f {
                float4 vertex : SV_POSITION;
                fixed4 color  : COLOR;
                float2 uv : TEXCOORD0;
                float4 worldPosition : TEXCOORD1; // 记录世界坐标用于裁切计算
            };

            sampler2D _MainTex;
            float _BlurSize;
            float4 _ClipRect; // Unity 会自动向这个变量传裁切框坐标

            v2f vert (appdata v) {
                v2f o;
                o.worldPosition = v.vertex;
                o.vertex = UnityObjectToClipPos(o.worldPosition);
                o.uv = v.uv;
                o.color = v.color;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target {
                float2 uv = i.uv;
                float d = _BlurSize * 0.005;
                
                fixed4 col = tex2D(_MainTex, uv);
                col += tex2D(_MainTex, uv + float2(d, d));
                col += tex2D(_MainTex, uv + float2(-d, d));
                col += tex2D(_MainTex, uv + float2(d, -d));
                col += tex2D(_MainTex, uv + float2(-d, -d));
                col /= 5.0;

                // --- 核心的一行：执行裁切测试 ---
                // 如果像素在 RectMask2D 之外，这里的 alpha 会被设为 0
                col.a *= UnityGet2DClipping(i.worldPosition.xy, _ClipRect);
                
                return col;
            }
            ENDCG
        }
    }
}