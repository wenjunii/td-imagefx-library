layout(location = 0) out vec4 fragColor;

uniform float uRadius;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = vec2(texel.x * max(uRadius, 0.0) * 0.5, 0.0);
    vec4 center = texture(sTD2DInputs[0], uv);
    vec3 glow = center.rgb * 0.375;
    glow += (texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb
           + texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb) * 0.25;
    glow += (texture(sTD2DInputs[0], clamp(uv + d * 2.0, vec2(0.0), vec2(1.0))).rgb
           + texture(sTD2DInputs[0], clamp(uv - d * 2.0, vec2(0.0), vec2(1.0))).rgb) * 0.0625;
    fragColor = TDOutputSwizzle(vec4(glow, center.a));
}
