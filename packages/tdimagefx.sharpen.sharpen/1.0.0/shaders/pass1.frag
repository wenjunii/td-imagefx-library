layout(location = 0) out vec4 fragColor;

uniform float uAmount;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec4 center = texture(sTD2DInputs[0], uv);
    vec3 left = texture(sTD2DInputs[0], clamp(uv - vec2(texel.x, 0.0), vec2(0.0), vec2(1.0))).rgb;
    vec3 right = texture(sTD2DInputs[0], clamp(uv + vec2(texel.x, 0.0), vec2(0.0), vec2(1.0))).rgb;
    float gain = max(uAmount, 0.0) * 0.5;
    vec3 enhanced = center.rgb * (1.0 + 2.0 * gain) - (left + right) * gain;
    fragColor = TDOutputSwizzle(vec4(enhanced, center.a));
}
