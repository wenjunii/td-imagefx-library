uniform float uMix;
uniform float uOpacity;
uniform float uPremultiplied;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 foreground = texture(sTD2DInputs[0], uv);
    vec4 background = texture(sTD2DInputs[1], uv);
    float fgAlpha = clamp(foreground.a * uOpacity, 0.0, 1.0);
    vec3 fgPremult = mix(foreground.rgb * fgAlpha, foreground.rgb * uOpacity, step(0.5, uPremultiplied));
    vec3 bgPremult = background.rgb * background.a;
    float outAlpha = fgAlpha + background.a * (1.0 - fgAlpha);
    vec3 outPremult = fgPremult + bgPremult * (1.0 - fgAlpha);
    vec3 outRgb = outPremult / max(outAlpha, 0.000001);
    vec4 composite = vec4(outRgb, outAlpha);
    fragColor = TDOutputSwizzle(mix(foreground, composite, clamp(uMix, 0.0, 1.0)));
}
