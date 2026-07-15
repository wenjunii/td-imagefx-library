layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uHue;
uniform float uSaturation;
uniform float uValue;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    vec3 hsv = TDRGBToHSV(source.rgb);
    hsv.x = fract(hsv.x + uHue);
    hsv.y = clamp(hsv.y * max(uSaturation, 0.0), 0.0, 1.0);
    hsv.z = max(hsv.z * max(uValue, 0.0), 0.0);
    vec4 effect = vec4(TDHSVToRGB(hsv), source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
