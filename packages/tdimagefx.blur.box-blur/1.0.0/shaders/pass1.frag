layout(location = 0) out vec4 fragColor;

uniform float uRadius;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 stepUv = vec2(texel.x * max(uRadius, 0.0) / 4.0, 0.0);
    vec4 center = texture(sTD2DInputs[0], uv);
    vec3 sum = vec3(0.0);
    for (int i = -4; i <= 4; ++i)
    {
        vec2 sampleUv = clamp(uv + stepUv * float(i), vec2(0.0), vec2(1.0));
        sum += texture(sTD2DInputs[0], sampleUv).rgb;
    }
    fragColor = TDOutputSwizzle(vec4(sum / 9.0, center.a));
}
