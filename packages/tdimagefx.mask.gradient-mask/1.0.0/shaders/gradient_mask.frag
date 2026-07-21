uniform float uMix;
uniform float uAngle;
uniform float uPosition;
uniform float uWidth;
uniform float uSoftness;
uniform float uInvert;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 direction = vec2(cos(uAngle), sin(uAngle));
    float coordinate = dot(uv - 0.5, direction) + 0.5;
    float halfWidth = max(uWidth * 0.5, 0.000001);
    float matte = smoothstep(uPosition - halfWidth, uPosition + halfWidth, coordinate);
    matte = pow(clamp(matte, 0.0, 1.0), max(uSoftness, 0.01));
    matte = mix(matte, 1.0 - matte, step(0.5, uInvert));
    vec4 masked = vec4(source.rgb, source.a * matte);
    fragColor = TDOutputSwizzle(mix(source, masked, clamp(uMix, 0.0, 1.0)));
}
