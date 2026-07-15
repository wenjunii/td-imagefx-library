layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uLevels;
uniform float uPatternScale;
uniform float uStrength;

const float ORDERED_PATTERN[16] = float[16](
    0.5, 8.5, 2.5, 10.5,
    12.5, 4.5, 14.5, 6.5,
    3.5, 11.5, 1.5, 9.5,
    15.5, 7.5, 13.5, 5.5
);

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    vec2 pixel = vUV.st * uTD2DInfos[0].res.zw;
    ivec2 patternCell = ivec2(mod(floor(pixel / max(uPatternScale, 1.0)), 4.0));
    int patternIndex = patternCell.y * 4 + patternCell.x;
    float threshold = ORDERED_PATTERN[patternIndex] / 16.0;
    float levelCount = max(floor(uLevels + 0.5), 2.0);
    vec3 quantized = floor(clamp(source.rgb, 0.0, 1.0) * (levelCount - 1.0) + threshold) / (levelCount - 1.0);
    vec3 dithered = mix(source.rgb, quantized, clamp(uStrength, 0.0, 1.0));
    vec4 effect = vec4(dithered, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
