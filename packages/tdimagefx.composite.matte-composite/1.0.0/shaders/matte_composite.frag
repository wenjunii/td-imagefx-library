uniform float uMix;
uniform float uBlack;
uniform float uWhite;
uniform float uInvert;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 foreground = texture(sTD2DInputs[0], uv);
    vec4 background = texture(sTD2DInputs[1], uv);
    float rawMatte = texture(sTD2DInputs[2], uv).r;
    float low = min(uBlack, uWhite);
    float high = max(uBlack, uWhite);
    float matte = smoothstep(low, max(high, low + 0.000001), rawMatte);
    matte = mix(matte, 1.0 - matte, step(0.5, uInvert));
    float fgAlpha = foreground.a * matte;
    float outAlpha = fgAlpha + background.a * (1.0 - fgAlpha);
    vec3 outPremult = foreground.rgb * fgAlpha + background.rgb * background.a * (1.0 - fgAlpha);
    vec3 outRgb = outPremult / max(outAlpha, 0.000001);
    vec4 composite = vec4(outRgb, outAlpha);
    fragColor = TDOutputSwizzle(mix(foreground, composite, clamp(uMix, 0.0, 1.0)));
}
