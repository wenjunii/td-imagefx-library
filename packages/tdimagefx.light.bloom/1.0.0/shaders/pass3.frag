layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uRadius;
uniform float uIntensity;

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 d = vec2(0.0, texel.y * max(uRadius, 0.0) * 0.25);
    vec3 bloom = texture(sTD2DInputs[0], uv).rgb * 0.2270270270;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d, vec2(0.0), vec2(1.0))).rgb) * 0.1945945946;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d * 2.0, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d * 2.0, vec2(0.0), vec2(1.0))).rgb) * 0.1216216216;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d * 3.0, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d * 3.0, vec2(0.0), vec2(1.0))).rgb) * 0.0540540541;
    bloom += (texture(sTD2DInputs[0], clamp(uv + d * 4.0, vec2(0.0), vec2(1.0))).rgb
            + texture(sTD2DInputs[0], clamp(uv - d * 4.0, vec2(0.0), vec2(1.0))).rgb) * 0.0162162162;
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 bloomed = original.rgb + bloom * max(uIntensity, 0.0);
    vec3 result = mix(original.rgb, bloomed, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
