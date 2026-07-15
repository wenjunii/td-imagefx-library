layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uSpread;
uniform float uIntensity;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = texel * max(uSpread, 0.0);
    vec3 halo = texture(sTD2DInputs[0], uv).rgb * 0.36;
    halo += texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb * 0.16;
    halo += texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb * 0.16;
    halo += texture(sTD2DInputs[0], clamp(uv + vec2(d.x, -d.y), vec2(0.0), vec2(1.0))).rgb * 0.16;
    halo += texture(sTD2DInputs[0], clamp(uv + vec2(-d.x, d.y), vec2(0.0), vec2(1.0))).rgb * 0.16;
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 glowed = original.rgb + halo * max(uIntensity, 0.0);
    vec3 result = mix(original.rgb, glowed, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
