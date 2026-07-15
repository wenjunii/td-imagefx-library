layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTime;
uniform float uAmount;
uniform float uFrequency;
uniform float uSpeed;
uniform float uAngle;

mat2 rotate2d(float angle)
{
    float s = sin(angle);
    float c = cos(angle);
    return mat2(c, -s, s, c);
}

void main()
{
    vec2 uv = vUV.st;
    vec2 centered = rotate2d(uAngle) * (uv - 0.5);
    float phase = uTime * uSpeed;
    vec2 displacement = vec2(
        sin((centered.y * uFrequency + phase) * 6.2831853),
        cos((centered.x * uFrequency - phase * 0.83) * 6.2831853)
    ) * uAmount;
    displacement = rotate2d(-uAngle) * displacement;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], uv + displacement);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
