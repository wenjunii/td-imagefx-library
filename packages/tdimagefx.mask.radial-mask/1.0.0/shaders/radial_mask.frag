uniform float uMix;
uniform vec2 uCenter;
uniform vec2 uSize;
uniform float uRotation;
uniform float uFeather;
uniform float uInvert;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float c = cos(-uRotation);
    float s = sin(-uRotation);
    vec2 local = mat2(c, -s, s, c) * (uv - uCenter);
    local /= max(abs(uSize) * 0.5, vec2(0.000001));
    float distanceFromCenter = length(local);
    float matte = 1.0 - smoothstep(1.0 - uFeather, 1.0 + uFeather, distanceFromCenter);
    matte = mix(matte, 1.0 - matte, step(0.5, uInvert));
    vec4 masked = vec4(source.rgb, source.a * matte);
    fragColor = TDOutputSwizzle(mix(source, masked, clamp(uMix, 0.0, 1.0)));
}
