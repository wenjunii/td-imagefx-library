layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uAmount;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec3 center = texture(sTD2DInputs[0], uv).rgb;
    vec3 down = texture(sTD2DInputs[0], clamp(uv - vec2(0.0, texel.y), vec2(0.0), vec2(1.0))).rgb;
    vec3 up = texture(sTD2DInputs[0], clamp(uv + vec2(0.0, texel.y), vec2(0.0), vec2(1.0))).rgb;
    float gain = max(uAmount, 0.0) * 0.5;
    vec3 sharpened = center * (1.0 + 2.0 * gain) - (down + up) * gain;
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 result = mix(original.rgb, sharpened, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
