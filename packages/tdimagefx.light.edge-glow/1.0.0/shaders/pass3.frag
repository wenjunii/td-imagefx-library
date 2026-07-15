layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uRadius;
uniform float uIntensity;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = vec2(0.0, texel.y * max(uRadius, 0.0) * 0.5);
    vec3 glow = texture(sTD2DInputs[0], uv).rgb * 0.375;
    glow += (texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb
           + texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb) * 0.25;
    glow += (texture(sTD2DInputs[0], clamp(uv + d * 2.0, vec2(0.0), vec2(1.0))).rgb
           + texture(sTD2DInputs[0], clamp(uv - d * 2.0, vec2(0.0), vec2(1.0))).rgb) * 0.0625;
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 glowing = original.rgb + glow * max(uIntensity, 0.0);
    vec3 result = mix(original.rgb, glowing, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
