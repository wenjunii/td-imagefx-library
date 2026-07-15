layout(location = 0) out vec4 fragColor;

uniform float uRadius;
uniform float uFocus;
uniform float uBandWidth;
uniform float uFeather;

void main()
{
    vec2 uv = vUV.st;
    float distanceFromBand = max(abs(uv.y - uFocus) - max(uBandWidth, 0.0), 0.0);
    float blurMask = smoothstep(0.0, max(uFeather, 0.001), distanceFromBand);
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 stepUv = vec2(texel.x * max(uRadius, 0.0) * blurMask / 3.0, 0.0);
    vec4 center = texture(sTD2DInputs[0], uv);
    vec3 sum = center.rgb * 0.24;
    sum += (texture(sTD2DInputs[0], clamp(uv + stepUv, vec2(0.0), vec2(1.0))).rgb
          + texture(sTD2DInputs[0], clamp(uv - stepUv, vec2(0.0), vec2(1.0))).rgb) * 0.20;
    sum += (texture(sTD2DInputs[0], clamp(uv + stepUv * 2.0, vec2(0.0), vec2(1.0))).rgb
          + texture(sTD2DInputs[0], clamp(uv - stepUv * 2.0, vec2(0.0), vec2(1.0))).rgb) * 0.12;
    sum += (texture(sTD2DInputs[0], clamp(uv + stepUv * 3.0, vec2(0.0), vec2(1.0))).rgb
          + texture(sTD2DInputs[0], clamp(uv - stepUv * 3.0, vec2(0.0), vec2(1.0))).rgb) * 0.06;
    fragColor = TDOutputSwizzle(vec4(sum, center.a));
}
