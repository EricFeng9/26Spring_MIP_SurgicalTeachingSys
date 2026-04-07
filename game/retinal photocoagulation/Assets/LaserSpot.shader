Shader "Custom/LaserSpot"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _CenterUV ("Center UV", Vector) = (0.5, 0.5, 0, 0)
        _RadiusUV ("Radius UV", Float) = 0.05
        _Grade ("Grade", Int) = 3
        _Aspect ("Aspect Ratio", Float) = 1.0 
        _BlurLevel ("Blur Level", Float) = 0.0 // 0 到 30 
    }
    SubShader
    {
        Cull Off ZWrite Off ZTest Always

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            float4 _MainTex_TexelSize;
            float2 _CenterUV;
            float _RadiusUV;
            int _Grade;
            float _Aspect;
            float _BlurLevel;

            struct v2f {
                float4 vertex : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            v2f vert (appdata_base v) {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = v.texcoord;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                // 1. 处理全局模糊：用 blur_level 控制采样步长，近似 Python 的 GaussianBlur 强度梯度
                float2 uv = i.uv;
                fixed4 col = fixed4(0,0,0,0);
                
                if (_BlurLevel > 0.1) {
                    float2 texel = _MainTex_TexelSize.xy;
                    float spread = _BlurLevel * 0.6;
                    float2 off1 = texel * spread;
                    float2 off2 = texel * spread * 2.0;
                    float2 off3 = texel * spread * 3.0;

                    col += tex2D(_MainTex, uv) * 0.227027;
                    col += tex2D(_MainTex, uv + float2(off1.x, 0)) * 0.1945946;
                    col += tex2D(_MainTex, uv - float2(off1.x, 0)) * 0.1945946;
                    col += tex2D(_MainTex, uv + float2(0, off1.y)) * 0.1945946;
                    col += tex2D(_MainTex, uv - float2(0, off1.y)) * 0.1945946;

                    col += tex2D(_MainTex, uv + float2(off2.x, 0)) * 0.1216216;
                    col += tex2D(_MainTex, uv - float2(off2.x, 0)) * 0.1216216;
                    col += tex2D(_MainTex, uv + float2(0, off2.y)) * 0.1216216;
                    col += tex2D(_MainTex, uv - float2(0, off2.y)) * 0.1216216;

                    col += tex2D(_MainTex, uv + off3) * 0.054054;
                    col += tex2D(_MainTex, uv - off3) * 0.054054;
                    col += tex2D(_MainTex, uv + float2(off3.x, -off3.y)) * 0.054054;
                    col += tex2D(_MainTex, uv + float2(-off3.x, off3.y)) * 0.054054;

                    col /= 1.7317024;
                } else {
                    col = tex2D(_MainTex, uv);
                }

                // 2. 激光斑绘制逻辑 (保持不变)
                float2 diff = uv - _CenterUV;
                diff.x *= _Aspect; 
                float distSq = dot(diff, diff);
                float radius = _RadiusUV;
                float sigmaSq = (radius / 2.0) * (radius / 2.0);
                if (sigmaSq <= 0) sigmaSq = 0.000001;
                float gaussianBase = exp(-distSq / (2.0 * sigmaSq));

                if (_Grade > 0) {
                    float3 spotColor = float3(210.0/255.0, 210.0/255.0, 210.0/255.0);
                    float alpha = 0;
                    if (_Grade == 1) alpha = gaussianBase * 0.3;
                    else if (_Grade == 2) alpha = gaussianBase * 0.65;
                    else if (_Grade == 3) {
                        alpha = gaussianBase * 0.85;
                        spotColor = float3(230.0/255.0, 230.0/255.0, 230.0/255.0);
                    }
                    else if (_Grade == 4) {
                        float halo = exp(-distSq / (2.0 * radius * radius)) * 0.5;
                        alpha = clamp(gaussianBase * 1.5 + halo, 0, 1);
                        spotColor = lerp(spotColor, float3(1,1,1), clamp(gaussianBase * 1.5, 0, 1));
                    }
                    col.rgb = lerp(col.rgb, spotColor, alpha);
                }
                return col;
            }
            ENDCG
        }
    }
}