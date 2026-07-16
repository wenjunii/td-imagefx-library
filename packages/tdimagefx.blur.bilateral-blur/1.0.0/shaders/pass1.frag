uniform float uRadius;
uniform float uSpatialSigma;
uniform float uRangeSigma;

layout(location = 0) out vec4 fragColor;

float rangeWeight(vec3 sampleColor, vec3 centerColor)
{
    vec3 difference = sampleColor - centerColor;
    return exp(-dot(difference, difference) / max(2.0 * uRangeSigma * uRangeSigma, 0.000001));
}

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / vec2(textureSize(sTD2DInputs[0], 0));
    vec4 center = texture(sTD2DInputs[0], uv);
    vec4 accumulated = center;
    float totalWeight = 1.0;
    for (int offset = 1; offset <= 12; ++offset) {
        if (float(offset) > uRadius + 0.001) break;
        float spatial = exp(-float(offset * offset) / max(2.0 * uSpatialSigma * uSpatialSigma, 0.000001));
        vec4 positive = texture(sTD2DInputs[0], uv + vec2(float(offset), 0.0) * texel);
        vec4 negative = texture(sTD2DInputs[0], uv - vec2(float(offset), 0.0) * texel);
        float positiveWeight = spatial * rangeWeight(positive.rgb, center.rgb);
        float negativeWeight = spatial * rangeWeight(negative.rgb, center.rgb);
        accumulated += positive * positiveWeight + negative * negativeWeight;
        totalWeight += positiveWeight + negativeWeight;
    }
    fragColor = TDOutputSwizzle(accumulated / max(totalWeight, 0.000001));
}
