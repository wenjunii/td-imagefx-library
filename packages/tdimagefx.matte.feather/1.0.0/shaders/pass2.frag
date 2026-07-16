uniform float uMix;
uniform float uRadius;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 horizontal = texture(sTD2DInputs[0], uv);
    vec4 source = texture(sTD2DInputs[1], uv);
    vec2 texel = 1.0 / vec2(textureSize(sTD2DInputs[0], 0));
    float radius = max(uRadius, 0.0001);
    float alpha = horizontal.a * 0.227027;
    alpha += texture(sTD2DInputs[0], uv + vec2(0.0, 1.384615 * radius) * texel).a * 0.316216;
    alpha += texture(sTD2DInputs[0], uv - vec2(0.0, 1.384615 * radius) * texel).a * 0.316216;
    alpha += texture(sTD2DInputs[0], uv + vec2(0.0, 3.230769 * radius) * texel).a * 0.070270;
    alpha += texture(sTD2DInputs[0], uv - vec2(0.0, 3.230769 * radius) * texel).a * 0.070270;
    vec4 feathered = vec4(source.rgb, alpha);
    fragColor = TDOutputSwizzle(mix(source, feathered, clamp(uMix, 0.0, 1.0)));
}
