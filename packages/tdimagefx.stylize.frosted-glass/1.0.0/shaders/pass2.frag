layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uSoftness;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = texel * max(uSoftness, 0.0);
    vec3 softened = texture(sTD2DInputs[0], uv).rgb * 0.20;
    softened += texture(sTD2DInputs[0], clamp(uv + vec2(d.x, 0.0), vec2(0.0), vec2(1.0))).rgb * 0.12;
    softened += texture(sTD2DInputs[0], clamp(uv - vec2(d.x, 0.0), vec2(0.0), vec2(1.0))).rgb * 0.12;
    softened += texture(sTD2DInputs[0], clamp(uv + vec2(0.0, d.y), vec2(0.0), vec2(1.0))).rgb * 0.12;
    softened += texture(sTD2DInputs[0], clamp(uv - vec2(0.0, d.y), vec2(0.0), vec2(1.0))).rgb * 0.12;
    softened += texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb * 0.08;
    softened += texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb * 0.08;
    softened += texture(sTD2DInputs[0], clamp(uv + vec2(d.x, -d.y), vec2(0.0), vec2(1.0))).rgb * 0.08;
    softened += texture(sTD2DInputs[0], clamp(uv + vec2(-d.x, d.y), vec2(0.0), vec2(1.0))).rgb * 0.08;
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 result = mix(original.rgb, softened, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
