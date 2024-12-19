const mongoose = require('mongoose');

const subSectionSchema = mongoose.Schema({
    title:{
        type:"String"
    },
    timeDuration:{
        type:"String"
    },
    videoUrl:{
        type:"String"
    },
    description:{
        type:"String"
    }
});
const SubSection = mongoose.models.SubSection || mongoose.model('SubSection', subSectionSchema);
module.exports = SubSection;

//module.exports = mongoose.model("SubSection",subSectionSchema);