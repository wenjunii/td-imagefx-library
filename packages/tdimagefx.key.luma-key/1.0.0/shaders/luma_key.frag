uniform float uMix;
uniform float uThreshold;
uniform float uSoftness;
uniform float uLowKey;
uniform float uInvert;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float luma = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    float matte = smoothstep(uThreshold - uSoftness, uThreshold + uSoftness, luma);
    matte = mix(matte, 1.0 - matte, step(0.5, uLowKey));
    matte = mix(matte, 1.0 - matte, step(0.5, uInvert));
    vec4 keyed = vec4(source.rgb, source.a * matte);
    fragColor = TDOutputSwizzle(mix(source, keyed, clamp(uMix, 0.0, 1.0)));
}
