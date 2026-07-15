layout(location = 0) out vec4 fragColor;

uniform float uRadius;

vec3 sampleRgb(vec2 uv)
{
    return texture(sTD2DInputs[0], clamp(uv, vec2(0.0), vec2(1.0))).rgb;
}

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 stepUv = vec2(texel.x * max(uRadius, 0.0) * 0.25, 0.0);
    vec4 center = texture(sTD2DInputs[0], uv);
    vec3 blurred = center.rgb * 0.2270270270;
    blurred += (sampleRgb(uv + stepUv) + sampleRgb(uv - stepUv)) * 0.1945945946;
    blurred += (sampleRgb(uv + stepUv * 2.0) + sampleRgb(uv - stepUv * 2.0)) * 0.1216216216;
    blurred += (sampleRgb(uv + stepUv * 3.0) + sampleRgb(uv - stepUv * 3.0)) * 0.0540540541;
    blurred += (sampleRgb(uv + stepUv * 4.0) + sampleRgb(uv - stepUv * 4.0)) * 0.0162162162;
    fragColor = TDOutputSwizzle(vec4(blurred, center.a));
}
