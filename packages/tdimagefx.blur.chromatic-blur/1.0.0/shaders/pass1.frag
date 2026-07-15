layout(location = 0) out vec4 fragColor;

uniform float uRadius;
uniform float uSeparation;

vec3 blurBand(vec2 uv, vec2 direction, float scale)
{
    vec2 d = direction * scale;
    vec3 sum = texture(sTD2DInputs[0], uv).rgb * 0.375;
    sum += (texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb
          + texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb) * 0.25;
    sum += (texture(sTD2DInputs[0], clamp(uv + d * 2.0, vec2(0.0), vec2(1.0))).rgb
          + texture(sTD2DInputs[0], clamp(uv - d * 2.0, vec2(0.0), vec2(1.0))).rgb) * 0.0625;
    return sum;
}

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 direction = vec2(texel.x * max(uRadius, 0.0) * 0.5, 0.0);
    float separation = clamp(uSeparation, 0.0, 1.0);
    vec3 wide = blurBand(uv, direction, 1.0 + separation);
    vec3 middle = blurBand(uv, direction, 1.0);
    vec3 narrow = blurBand(uv, direction, max(1.0 - separation, 0.05));
    vec4 source = texture(sTD2DInputs[0], uv);
    fragColor = TDOutputSwizzle(vec4(wide.r, middle.g, narrow.b, source.a));
}
