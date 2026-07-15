layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uAmount;
uniform float uAngle;
uniform float uGreenOffset;

void main()
{
    vec2 uv = vUV.st;
    vec2 direction = vec2(cos(uAngle), sin(uAngle)) * uAmount;
    vec4 source = texture(sTD2DInputs[0], uv);
    float red = texture(sTD2DInputs[0], uv + direction).r;
    float green = texture(sTD2DInputs[0], uv + direction * uGreenOffset).g;
    float blue = texture(sTD2DInputs[0], uv - direction).b;
    vec4 effect = vec4(red, green, blue, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
