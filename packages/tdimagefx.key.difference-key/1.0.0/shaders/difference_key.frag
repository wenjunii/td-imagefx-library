uniform float uMix;
uniform float uThreshold;
uniform float uSoftness;
uniform float uLumaWeight;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 foreground = texture(sTD2DInputs[0], uv);
    vec3 reference = texture(sTD2DInputs[1], uv).rgb;
    vec3 delta = abs(foreground.rgb - reference);
    float rgbDistance = length(delta) * 0.57735026919;
    float lumaDistance = abs(dot(delta, vec3(0.2126, 0.7152, 0.0722)));
    float difference = mix(rgbDistance, lumaDistance, clamp(uLumaWeight, 0.0, 1.0));
    float matte = smoothstep(uThreshold, uThreshold + max(uSoftness, 0.000001), difference);
    vec4 keyed = vec4(foreground.rgb, foreground.a * matte);
    fragColor = TDOutputSwizzle(mix(foreground, keyed, clamp(uMix, 0.0, 1.0)));
}
