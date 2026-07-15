layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uRadius;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 stepUv = vec2(0.0, texel.y * max(uRadius, 0.0) / 4.0);
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 sum = vec3(0.0);
    for (int i = -4; i <= 4; ++i)
    {
        vec2 sampleUv = clamp(uv + stepUv * float(i), vec2(0.0), vec2(1.0));
        sum += texture(sTD2DInputs[0], sampleUv).rgb;
    }
    vec3 blurred = sum / 9.0;
    vec3 result = mix(original.rgb, blurred, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
