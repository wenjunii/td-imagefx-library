layout(location = 0) out vec4 fragColor;

uniform float uRadius;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = vec2(texel.x * max(uRadius, 0.0) * 0.25, 0.0);
    vec4 center = texture(sTD2DInputs[0], uv);
    vec3 bloom = center.rgb * 0.2270270270;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb) * 0.1945945946;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d * 2.0, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d * 2.0, vec2(0.0), vec2(1.0))).rgb) * 0.1216216216;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d * 3.0, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d * 3.0, vec2(0.0), vec2(1.0))).rgb) * 0.0540540541;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d * 4.0, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d * 4.0, vec2(0.0), vec2(1.0))).rgb) * 0.0162162162;
    fragColor = TDOutputSwizzle(vec4(bloom, center.a));
}
