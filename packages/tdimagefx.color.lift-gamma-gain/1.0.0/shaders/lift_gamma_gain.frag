layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uLiftR;
uniform float uLiftG;
uniform float uLiftB;
uniform float uGammaR;
uniform float uGammaG;
uniform float uGammaB;
uniform float uGainR;
uniform float uGainG;
uniform float uGainB;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    vec3 lift = vec3(uLiftR, uLiftG, uLiftB);
    vec3 gammaValue = max(vec3(uGammaR, uGammaG, uGammaB), vec3(0.00001));
    vec3 gain = max(vec3(uGainR, uGainG, uGainB), vec3(0.0));
    vec3 raised = max(source.rgb + lift, vec3(0.0));
    vec3 corrected = pow(raised, vec3(1.0) / gammaValue) * gain;
    vec4 effect = vec4(corrected, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
