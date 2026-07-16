uniform float uMix;
uniform float uRadius;
uniform float uSamples;
uniform float uBlades;
uniform float uHighlight;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 texel = 1.0 / vec2(textureSize(sTD2DInputs[0], 0));
    vec4 accumulated = source;
    float totalWeight = 1.0;
    float sampleCount = clamp(floor(uSamples + 0.5), 6.0, 32.0);
    float bladeCount = clamp(floor(uBlades + 0.5), 3.0, 12.0);
    const float goldenAngle = 2.39996322973;
    for (int index = 1; index <= 32; ++index) {
        if (float(index) > sampleCount) break;
        float normalizedIndex = float(index) / sampleCount;
        float angle = float(index) * goldenAngle;
        float sector = 6.28318530718 / bladeCount;
        float aperture = cos(3.14159265359 / bladeCount) / max(cos(mod(angle + sector * 0.5, sector) - sector * 0.5), 0.0001);
        float radius = sqrt(normalizedIndex) * uRadius * aperture;
        vec4 sampleValue = texture(sTD2DInputs[0], uv + vec2(cos(angle), sin(angle)) * texel * radius);
        float luminance = dot(sampleValue.rgb, vec3(0.2126, 0.7152, 0.0722));
        float weight = 1.0 + max(luminance - 1.0, 0.0) * uHighlight;
        accumulated += sampleValue * weight;
        totalWeight += weight;
    }
    vec4 blurred = accumulated / max(totalWeight, 0.000001);
    fragColor = TDOutputSwizzle(mix(source, blurred, clamp(uMix, 0.0, 1.0)));
}
