uniform float uMix;
uniform float uRadius;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 texel = 1.0 / vec2(textureSize(sTD2DInputs[0], 0));
    float alpha = source.a;
    for (int y = -8; y <= 8; ++y) {
        for (int x = -8; x <= 8; ++x) {
            if (length(vec2(x, y)) > uRadius + 0.001) continue;
            alpha = min(alpha, texture(sTD2DInputs[0], uv + vec2(x, y) * texel).a);
        }
    }
    vec4 eroded = vec4(source.rgb, alpha);
    fragColor = TDOutputSwizzle(mix(source, eroded, clamp(uMix, 0.0, 1.0)));
}
