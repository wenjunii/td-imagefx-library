uniform float uMix;
uniform float uFocus;
uniform float uAperture;
uniform float uMaxRadius;
uniform float uEdgeTolerance;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float centerDepth = texture(sTD2DInputs[1], uv).r;
    vec2 texel = 1.0 / vec2(textureSize(sTD2DInputs[0], 0));
    float blurRadius = min(abs(centerDepth - uFocus) * uAperture * uMaxRadius, uMaxRadius);
    vec4 accumulated = source;
    float totalWeight = 1.0;
    const float goldenAngle = 2.39996322973;
    for (int index = 1; index <= 24; ++index) {
        float normalizedIndex = float(index) / 24.0;
        float angle = float(index) * goldenAngle;
        vec2 offset = vec2(cos(angle), sin(angle)) * sqrt(normalizedIndex) * blurRadius * texel;
        float sampleDepth = texture(sTD2DInputs[1], uv + offset).r;
        float depthWeight = exp(-abs(sampleDepth - centerDepth) / max(uEdgeTolerance, 0.000001));
        vec4 sampleValue = texture(sTD2DInputs[0], uv + offset);
        accumulated += sampleValue * depthWeight;
        totalWeight += depthWeight;
    }
    vec4 blurred = accumulated / max(totalWeight, 0.000001);
    fragColor = TDOutputSwizzle(mix(source, blurred, clamp(uMix, 0.0, 1.0)));
}
