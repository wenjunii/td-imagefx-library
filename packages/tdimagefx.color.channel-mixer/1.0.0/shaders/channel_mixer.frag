layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uRedFromRed;
uniform float uRedFromGreen;
uniform float uRedFromBlue;
uniform float uGreenFromRed;
uniform float uGreenFromGreen;
uniform float uGreenFromBlue;
uniform float uBlueFromRed;
uniform float uBlueFromGreen;
uniform float uBlueFromBlue;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    vec3 mapped = vec3(
        dot(source.rgb, vec3(uRedFromRed, uRedFromGreen, uRedFromBlue)),
        dot(source.rgb, vec3(uGreenFromRed, uGreenFromGreen, uGreenFromBlue)),
        dot(source.rgb, vec3(uBlueFromRed, uBlueFromGreen, uBlueFromBlue))
    );
    vec4 effect = vec4(max(mapped, vec3(0.0)), source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
