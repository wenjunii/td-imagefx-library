layout(location = 0) out vec4 fragColor;

uniform float uSpread;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = texel * max(uSpread, 0.0) * 0.5;
    vec4 center = texture(sTD2DInputs[0], uv);
    vec3 halo = center.rgb * 0.20;
    halo += texture(sTD2DInputs[0], clamp(uv + vec2(d.x, 0.0), vec2(0.0), vec2(1.0))).rgb * 0.12;
    halo += texture(sTD2DInputs[0], clamp(uv - vec2(d.x, 0.0), vec2(0.0), vec2(1.0))).rgb * 0.12;
    halo += texture(sTD2DInputs[0], clamp(uv + vec2(0.0, d.y), vec2(0.0), vec2(1.0))).rgb * 0.12;
    halo += texture(sTD2DInputs[0], clamp(uv - vec2(0.0, d.y), vec2(0.0), vec2(1.0))).rgb * 0.12;
    halo += texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb * 0.08;
    halo += texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb * 0.08;
    halo += texture(sTD2DInputs[0], clamp(uv + vec2(d.x, -d.y), vec2(0.0), vec2(1.0))).rgb * 0.08;
    halo += texture(sTD2DInputs[0], clamp(uv + vec2(-d.x, d.y), vec2(0.0), vec2(1.0))).rgb * 0.08;
    fragColor = TDOutputSwizzle(vec4(halo, center.a));
}
