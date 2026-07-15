layout(location = 0) out vec4 fragColor;

uniform float uRadius;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = vec2(0.0, texel.y * max(uRadius, 0.0));
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 blurred = texture(sTD2DInputs[0], uv).rgb * 0.375;
    blurred += (texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb
              + texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb) * 0.25;
    blurred += (texture(sTD2DInputs[0], clamp(uv + d * 2.0, vec2(0.0), vec2(1.0))).rgb
              + texture(sTD2DInputs[0], clamp(uv - d * 2.0, vec2(0.0), vec2(1.0))).rgb) * 0.0625;
    fragColor = TDOutputSwizzle(vec4(blurred, original.a));
}
