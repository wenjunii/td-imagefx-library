uniform float uMix;
uniform float uRadius;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 texel = 1.0 / vec2(textureSize(sTD2DInputs[0], 0));
    vec4 best = source;
    for (int y = -8; y <= 8; ++y) {
        for (int x = -8; x <= 8; ++x) {
            if (length(vec2(x, y)) > uRadius + 0.001) continue;
            vec4 sampleValue = texture(sTD2DInputs[0], uv + vec2(x, y) * texel);
            if (sampleValue.a > best.a) best = sampleValue;
        }
    }
    fragColor = TDOutputSwizzle(mix(source, best, clamp(uMix, 0.0, 1.0)));
}
